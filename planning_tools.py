"""Offline portability, summaries, duplication, and short-lived deletion recovery.

Backups use validated JSON rather than a raw database file. Imports always add
independent copies, remapping record IDs in one transaction. No network access.
"""
import base64
import copy
import json
from trip_store import (validate_trip, validate_expense, validate_traveler, money,
                        expense_total_cents, display_date, MAX_PHOTO_BYTES)

MAX_BACKUP_BYTES = 64 * 1024 * 1024


def dollar_string(cents):
    return f'{cents // 100}.{cents % 100:02d}'


def export_trip(store, trip_id):
    """Capture active records plus saved/removed-traveler allocations."""
    trip = store.get(trip_id)
    if not trip:
        raise ValueError('This trip no longer exists.')
    travelers = []
    for traveler in store.travelers(trip_id):
        traveler = dict(traveler)
        image = traveler.pop('image_bytes', None)
        traveler['photo_base64'] = base64.b64encode(image).decode('ascii') if image else None
        travelers.append(traveler)
    return dict(trip=trip, travelers=travelers,
                expenses=[dict(record=expense, shares=store.expense_shares(trip_id, expense['id']))
                          for expense in store.expenses(trip_id)])


def backup_text(store, trip_ids=None):
    ids = trip_ids if trip_ids is not None else [trip['id'] for trip in store.all()]
    return json.dumps(dict(format='trip-planner', version=1, trips=[export_trip(store, tid) for tid in ids]), indent=2)


def integer(value, caption, minimum=0, maximum=10**15):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'Invalid {caption} in backup.')
    return value


def validate_bundle(bundle):
    """Validate the full graph before import writes any rows."""
    if not isinstance(bundle, dict) or not isinstance(bundle.get('trip'), dict):
        raise ValueError('Invalid trip in backup.')
    raw = bundle['trip']
    budget = integer(raw.get('cost_cents'), 'budget')
    people = integer(raw.get('people'), 'headcount', 1, 999)
    trip = validate_trip(str(raw.get('name', '')), str(raw.get('destination', '')),
                         dollar_string(budget) if raw.get('budget_set', 1) else '', str(people),
                         str(raw.get('description', '')), str(raw.get('start_date', '')), str(raw.get('end_date', '')))
    profiles, expenses = bundle.get('travelers'), bundle.get('expenses')
    if not isinstance(profiles, list) or len(profiles) > 999 or not isinstance(expenses, list) or len(expenses) > 5000:
        raise ValueError('Invalid or oversized trip contents.')
    travelers, ids = [], set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError('Invalid traveler in backup.')
        tid = integer(profile.get('id'), 'traveler ID', 1)
        if tid in ids:
            raise ValueError('Duplicate traveler ID in backup.')
        ids.add(tid)
        encoded = profile.get('photo_base64')
        if encoded and (not isinstance(encoded, str) or len(encoded) > MAX_PHOTO_BYTES * 4 // 3 + 4):
            raise ValueError('Photo too large in backup.')
        try:
            photo = base64.b64decode(encoded, validate=True) if encoded else None
        except (ValueError, TypeError):
            raise ValueError('Invalid photo in backup.') from None
        data = validate_traveler(str(profile.get('name', '')), '' if profile.get('age') is None else str(profile['age']),
                                 str(profile.get('phone', '')), str(profile.get('email', '')), str(profile.get('gender', '')), photo)
        travelers.append((tid, data))
    checked_expenses, expense_ids = [], set()
    for item in expenses:
        if not isinstance(item, dict) or not isinstance(item.get('record'), dict):
            raise ValueError('Invalid expense in backup.')
        record = item['record']
        eid = integer(record.get('id'), 'expense ID', 1)
        if eid in expense_ids:
            raise ValueError('Duplicate expense ID in backup.')
        expense_ids.add(eid)
        amount = integer(record.get('cost_cents'), 'expense cost')
        values = {key: record.get(key, '') for key in store_expense_keys()}
        expense = validate_expense(name=str(record.get('name', '')), cost=dollar_string(amount), **values)
        count = integer(record.get('split_count'), 'participant count', 1, 999)
        shares = item.get('shares')
        if not isinstance(shares, list) or len(shares) > 999:
            raise ValueError('Invalid allocations in backup.')
        allocations, seen = [], set()
        for share in shares:
            if not isinstance(share, dict):
                raise ValueError('Invalid allocation in backup.')
            tid = share.get('traveler_id')
            if tid is not None and (type(tid) is not int or tid not in ids or tid in seen):
                raise ValueError('Allocation refers to a missing or duplicated traveler.')
            seen.add(tid) if tid is not None else None
            name = str(share.get('name') or share.get('traveler_name') or '').strip()
            if not name or len(name) > 80:
                raise ValueError('Invalid allocation name.')
            allocations.append((tid, name, integer(share.get('amount_cents'), 'share')))
        if allocations and sum(share[2] for share in allocations) != expense_total_cents(dict(expense, split_count=count), people):
            raise ValueError('Expense shares do not match its total.')
        if allocations and len(allocations) != count:
            raise ValueError('Allocation count does not match the saved split.')
        checked_expenses.append((expense, count, int(bool(record.get('split_review')) or not allocations), allocations))
    return trip, travelers, checked_expenses


def store_expense_keys():
    from trip_store import EXPENSE_DETAILS
    return ('description', 'category', 'cost_basis', 'split_mode', 'cost_status', 'flight_segments') + EXPENSE_DETAILS


def import_backup(store, document):
    """Validate then atomically append copies; never overwrite current trips."""
    if not isinstance(document, str) or len(document.encode('utf-8')) > MAX_BACKUP_BYTES:
        raise ValueError('Backup exceeds 64 MB.')
    try:
        root = json.loads(document)
        if not isinstance(root, dict) or root.get('format') != 'trip-planner' or root.get('version') != 1:
            raise ValueError('Unsupported backup format or version.')
        bundles = root.get('trips')
        if not isinstance(bundles, list) or not 1 <= len(bundles) <= 100:
            raise ValueError('A backup must contain 1 to 100 trips.')
        checked = [validate_bundle(bundle) for bundle in bundles]
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError('The backup is malformed or contains invalid fields.') from error
    new_ids = []
    with store.connect() as db:
        for trip, profiles, expenses in checked:
            values = [trip[key] for key in store.fields]
            tid = db.execute('INSERT INTO trips (' + ','.join(store.fields) + ') VALUES (' + ','.join('?' for _ in values) + ')', values).lastrowid
            new_ids.append(tid)
            mapping = {}
            fields = ('name', 'age', 'phone', 'email', 'gender', 'image_bytes')
            for old_id, profile in profiles:
                mapping[old_id] = db.execute('INSERT INTO travelers (' + ','.join(fields) + ',trip_id) VALUES (?,?,?,?,?,?,?)',
                                             [profile[key] for key in fields] + [tid]).lastrowid
            for expense, count, review, shares in expenses:
                fields = store.expense_fields + ('trip_id', 'split_count', 'split_review')
                values = [expense[key] for key in store.expense_fields] + [tid, count, review]
                eid = db.execute('INSERT INTO expenses (' + ','.join(fields) + ') VALUES (' + ','.join('?' for _ in values) + ')', values).lastrowid
                db.executemany('INSERT INTO expense_shares VALUES (?,?,?,?)',
                               [(eid, mapping.get(profile_id), name, cents) for profile_id, name, cents in shares])
    return new_ids


def duplicate_trip(store, trip_id, clear_dates=False, reset_confirmed=True):
    """Copy the complete graph with new IDs and independently editable records."""
    bundle = copy.deepcopy(export_trip(store, trip_id))
    bundle['trip']['name'] = bundle['trip']['name'][:73] + ' (copy)'
    if clear_dates:
        bundle['trip']['start_date'] = bundle['trip']['end_date'] = ''
    for item in bundle['expenses']:
        expense = item['record']
        if reset_confirmed:
            expense['cost_status'] = 'estimated'
        if clear_dates:
            for key in ('expense_date', 'departure_at', 'arrival_at', 'check_in', 'check_out'):
                expense[key] = ''
            segments = json.loads(expense['flight_segments'])
            for segment in segments:
                segment['departure_at'] = segment['arrival_at'] = ''
            expense['flight_segments'] = json.dumps(segments)
    return import_backup(store, json.dumps(dict(format='trip-planner', version=1, trips=[bundle])))[0]


def trip_summary(store, trip_id):
    """Readable cost summary; deliberately exclude contact details and photos."""
    trip = store.get(trip_id)
    if not trip:
        raise ValueError('This trip no longer exists.')
    total = store.expense_total(trip_id)
    lines = [trip['name'], 'Destinations: ' + (trip['destination'].replace('\n', ' > ') or 'Undecided'),
             f"Dates: {display_date(trip['start_date'])} - {display_date(trip['end_date'])}",
             'Budget: ' + (money(trip['cost_cents']) + ' USD' if trip['budget_set'] else 'Not set'),
             f'Planned cost so far: {money(total)} USD (expense list may be incomplete)', '', 'Expenses:']
    for expense in store.expenses(trip_id):
        lines.append(f"- {expense['name']} [{expense['category']}, {expense['cost_status']}] {money(expense_total_cents(expense, trip['people']))} USD")
        if expense['split_review']:
            lines.append('  Split needs review / may contain unassigned or removed-traveler shares.')
    lines += ['', 'Traveler shares:']
    for traveler in store.travelers(trip_id):
        share = sum(row['amount_cents'] for row in store.traveler_shares(trip_id, traveler['id']))
        lines.append(f"- {traveler['name']}: {money(share)} USD")
    if trip['description']:
        lines += ['', 'Notes:', trip['description']]
    lines.append('\nConfirmed means the price is known, not that it has been paid.')
    return '\n'.join(lines)


def stage_delete(store, kind, record_id):
    """Hide a record while retaining its IDs/relationships for the Undo window."""
    if kind not in ('trips', 'expenses', 'travelers'):
        raise ValueError('Invalid deletion type.')
    with store.connect() as db:
        record = db.execute(f'SELECT * FROM {kind} WHERE id=? AND pending_delete=0', (record_id,)).fetchone()
        if not record:
            raise ValueError('This item no longer exists.')
        review_states, roster = [], []
        if kind == 'travelers':
            roster = [row['id'] for row in db.execute('SELECT id FROM travelers WHERE trip_id=? AND pending_delete=0 ORDER BY id', (record['trip_id'],))]
            for expense in db.execute('SELECT id,split_review FROM expenses WHERE id IN (SELECT expense_id FROM expense_shares WHERE traveler_id=?)', (record_id,)).fetchall():
                allocations = [tuple(row) for row in db.execute('SELECT traveler_id,traveler_name,amount_cents FROM expense_shares WHERE expense_id=? ORDER BY rowid', (expense['id'],))]
                review_states.append((expense['id'], expense['split_review'], allocations))
                db.execute('UPDATE expenses SET split_review=1 WHERE id=?', (expense['id'],))
        db.execute(f'UPDATE {kind} SET pending_delete=1 WHERE id=?', (record_id,))
    return dict(kind=kind, id=record_id, trip_id=record_id if kind == 'trips' else record['trip_id'], review_states=review_states, roster=roster)


def stage_trip_deletions(store, trip_ids):
    """Hide a group atomically and return one token that restores every trip.

    Validate the whole selection first. Children remain intact during Undo;
    normal startup cleanup also finalizes a group if the app closes early.
    """
    ids = sorted(set(trip_ids))
    if not ids:
        raise ValueError('Select at least one trip.')
    with store.connect() as db:
        for trip_id in ids:
            if not db.execute('SELECT id FROM trips WHERE id=? AND pending_delete=0', (trip_id,)).fetchone():
                raise ValueError('A selected trip no longer exists. Please select again.')
        db.executemany('UPDATE trips SET pending_delete=1 WHERE id=?', [(tid,) for tid in ids])
    return dict(kind='trip_batch', ids=ids)


def finish_delete(store, token, undo=False):
    """Undo restores the original row; expiration uses existing cascade rules."""
    if token['kind'] == 'trip_batch':
        # One transaction keeps restoration/finalization all-or-nothing, just
        # like staging. Cascades remove each trip's children on expiration.
        with store.connect() as db:
            statement = ('UPDATE trips SET pending_delete=0 WHERE id=? AND pending_delete=1' if undo
                         else 'DELETE FROM trips WHERE id=? AND pending_delete=1')
            db.executemany(statement, [(tid,) for tid in token['ids']])
        return
    kind, record_id = token['kind'], token['id']
    if kind not in ('trips', 'expenses', 'travelers'):
        raise ValueError('Invalid deletion type.')
    if undo:
        with store.connect() as db:
            db.execute(f'UPDATE {kind} SET pending_delete=0 WHERE id=?', (record_id,))
            if kind == 'travelers':
                roster = [row['id'] for row in db.execute('SELECT id FROM travelers WHERE trip_id=? AND pending_delete=0 ORDER BY id', (token['trip_id'],))]
                if roster == token['roster']:
                    for eid, old_review, previous in token['review_states']:
                        current = [tuple(row) for row in db.execute('SELECT traveler_id,traveler_name,amount_cents FROM expense_shares WHERE expense_id=? ORDER BY rowid', (eid,))]
                        if current == previous:
                            db.execute('UPDATE expenses SET split_review=? WHERE id=?', (old_review, eid))
    elif kind == 'trips':
        store.delete(record_id)
    elif kind == 'expenses':
        store.delete_expense(token['trip_id'], record_id)
    else:
        store.delete_traveler(token['trip_id'], record_id)
