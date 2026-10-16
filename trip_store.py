"""Trip Planner's data layer: validation, money calculations, and SQLite storage.

Forms pass strings to validate_* functions, which return dictionaries suitable
for TripStore.save_* methods. Validation failures raise ValueError with a
message the UI can show directly. Money is stored as integer cents; photos are
stored as bytes. This module never imports Kivy, so its rules can be tested
without opening a window. See docs/CODE_GUIDE.md for common change recipes.
"""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from contextlib import contextmanager
import re
import sqlite3
import json

MAX_PHOTO_BYTES = 10 * 1024 * 1024
# These names are both dropdown choices and saved category values. Renaming one
# requires updating existing records, not just changing the visible label.
EXPENSE_CATEGORIES = ('Flights', 'Lodging', 'Food & drink', 'Transportation', 'Activities', 'Other')
# Keep this order aligned with validate_expense's details tuple and SQL fields.
EXPENSE_DETAILS = ('expense_date', 'provider', 'airline', 'flight_number', 'departure_airport',
                   'arrival_airport', 'departure_at', 'arrival_at', 'check_in', 'check_out')
# TODO: Change arrival_at to return at and subsequent Arrival date & time TO Return date & time

MONTH_NAMES = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def display_date(value):
    """Format an ISO date/datetime for display without changing stored values."""
    if not value:
        return 'Not set'
    part, _, time = value.partition(' ')
    parsed = date.fromisoformat(part)
    formatted = f'{MONTH_NAMES[parsed.month - 1]} {parsed.day}, {parsed.year:04d}'
    return formatted + (f' at {time}' if time else '')


def parse_cost(value, max_digits=9, caption='cost'):
    """Convert dollars to cents, accepting plain digits or grouped commas.

    Commas must separate groups of three digits: 1,250.00 is valid, 12,50 is
    not. Decimal avoids floating-point errors, including for custom shares.
    """
    value = str(value).strip()
    if not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?', value):
        raise ValueError(f'Enter a {caption} like 1250.00 or 1,250.00 (USD).')
    normalized = value.replace(',', '')
    if len(normalized.split('.')[0]) > max_digits:
        raise ValueError(f'The {caption} is too large; use up to {max_digits} dollar digits.')
    return int(Decimal(normalized) * 100)

def expense_total_cents(expense, people):
    """Return the group total in cents using the saved participant count.

    cost_cents is the entered price: a group total or a per-person rate.
    people is only a fallback when no saved split_count exists yet.
    """
    count = expense.get('split_count', 0) or people
    return expense['cost_cents'] * count if expense.get('cost_basis', 'group') == 'per_person' else expense['cost_cents']


def calculate_split(expense, people, travelers, participant_ids=None, custom_amounts=None):
    """Return (participant_count, {traveler_id: share_in_cents}).

    Everyone uses all supplied profiles; selected/custom use participant_ids.
    Custom amounts are dollar strings, such as {12: '70.00', 13: '30.00'}.
    With no profiles, Everyone returns the planned count and an empty mapping;
    storage marks that expense for review rather than inventing named shares.
    Invalid participants or amounts raise ValueError before any data is saved.
    """
    mode = expense.get('split_mode', 'everyone')
    if mode not in ('everyone', 'selected', 'custom'):
        raise ValueError('Choose Everyone, Selected travelers, or Custom amounts.')
    valid_ids = {traveler['id'] for traveler in travelers}
    ids = sorted(valid_ids if mode == 'everyone' else (participant_ids or []))
    if len(ids) != len(set(ids)) or any(tid not in valid_ids for tid in ids):
        raise ValueError('Choose travelers belonging to this trip.')
    if not ids and mode != 'everyone':
        raise ValueError('Select at least one traveler for this expense.')
    count = len(ids) or people
    total = expense_total_cents(dict(expense, split_count=count), people)
    if mode == 'custom':
        amounts = custom_amounts or {}
        if any(tid not in ids for tid in amounts):
            raise ValueError('Enter amounts only for selected travelers.')
        shares = {}
        for tid in ids:
            value = str(amounts.get(tid, '')).strip()
            shares[tid] = parse_cost(value, max_digits=12, caption='traveler share (use 0 for no charge)')
        if sum(shares.values()) != total:
            raise ValueError(f'Custom shares must add up to {money(total)} USD.')
    else:
        # Integer division avoids floating-point rounding. The first IDs receive
        # one extra cent each until the remainder is used: $10 / 3 becomes
        # $3.34, $3.33, $3.33, and always adds up to exactly $10.
        cents, remainder = divmod(total, len(ids)) if ids else (0, 0)
        shares = {tid: cents + (index < remainder) for index, tid in enumerate(ids)}
    return count, shares


def validate_optional_date(value, caption):
    """Accept blank or a real YYYY-MM-DD date; caption names the error field."""
    if value:
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                raise ValueError()
            date.fromisoformat(value)
        except ValueError:
            raise ValueError(f'Use a valid {caption} in YYYY-MM-DD format.') from None


def photo_format(data):
    """Identify PNG/JPEG bytes by their header; image decoding happens in the UI."""
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    raise ValueError('Choose a PNG or JPEG photo.')

# Error messages for Traveler INFO
def validate_traveler(name, age='', phone='', email='', gender='', image_bytes=None):
    """Normalize profile fields; require only a name and return age as int or None.

    Phone and email checks validate basic formatting, not whether they exist.
    image_bytes is None when there is no photo, otherwise original file bytes.
    """
    name, age, phone, email, gender = (str(value).strip() for value in (name, age, phone, email, gender))
    if not name or len(name) > 80:
        raise ValueError('Enter a traveler name of up to 80 characters.')
    if age and (not re.fullmatch(r'\d{1,3}', age) or not 0 <= int(age) <= 120):
        raise ValueError('Enter an age from 0 to 120, or leave it blank.')
    if phone and (len(phone) > 40 or not re.fullmatch(r'[+\d\s().xX#-]+', phone) or sum(c.isdigit() for c in phone) < 3):
        raise ValueError('Enter a phone number, or leave it blank.')
    if email and (len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email)):
        raise ValueError('Enter an email like name@example.com, or leave it blank.')
    if len(gender) > 80:
        raise ValueError('Keep gender to 80 characters or fewer.')
    if image_bytes is not None:
        if not isinstance(image_bytes, bytes) or len(image_bytes) > MAX_PHOTO_BYTES:
            raise ValueError('Choose a photo smaller than 10 MB.')
        photo_format(image_bytes)
    return dict(name=name, age=int(age) if age else None, phone=phone, email=email,
                gender=gender, image_bytes=image_bytes)


def validate_trip(name, destination='', cost='', people='1', description='', start_date='', end_date=''):
    """Validate form strings and return a trip record with cents and integer people.

    Only name is required. Blank cost means budget_set=0; a typed zero is a
    set budget of $0. Blank headcount defaults to one. Destination lines keep
    their entered order. The budget is independent of saved expense totals.
    Optional dates must be provided together and form a nondecreasing range.
    """
    name, destination = name.strip(), destination.strip()
    if not name:
        raise ValueError('Enter a trip name.')
    stops = [stop.strip() for stop in destination.splitlines() if stop.strip()]
    if len(name) > 80 or len(stops) > 20 or any(len(stop) > 160 for stop in stops) or len(description) > 2000:
        raise ValueError('Use up to 80 characters for the name, 20 destinations of 160 characters, and 2,000 for notes.')
    destination = '\n'.join(stops)
    budget_set = bool(cost.strip())
    cost_cents = parse_cost(cost, caption='trip budget') if budget_set else 0
    people = people.strip() or '1'
    if not re.fullmatch(r'\d{1,3}', people) or not 1 <= int(people) <= 999:
        raise ValueError('Enter 1 to 999 people, including yourself.')
    start_date, end_date = start_date.strip(), end_date.strip()
    if bool(start_date) != bool(end_date):
        raise ValueError('Enter both dates, or leave both blank.')
    if start_date:
        try:
            if not all(re.fullmatch(r'\d{4}-\d{2}-\d{2}', d) for d in (start_date, end_date)):
                raise ValueError()
            start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        except ValueError:
            raise ValueError('Use valid dates in YYYY-MM-DD format.') from None
        if end < start:
            raise ValueError('End date must be on or after the start date.')
    return dict(name=name, destination=destination, cost_cents=cost_cents,
                people=int(people), description=description.strip(), start_date=start_date, end_date=end_date, budget_set=int(budget_set))


def money(cents, people=1):
    """Format cents as dollars; optional division produces a displayed average.

    This rounds for display only. Use calculate_split for actual allocations
    whose individual shares must add up to the original total.
    """
    amount = (Decimal(cents) / 100 / people).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return f'${amount:,.2f}'


def validate_expense(name, cost, description='', category='Other', cost_basis='group',
                     expense_date='', provider='', airline='', flight_number='', departure_airport='',
                     arrival_airport='', departure_at='', arrival_at='', check_in='', check_out='', split_mode='everyone',
                     cost_status='estimated', flight_segments=None):
    """Validate expense fields without calculating participant shares.

    Return cost_cents as the entered rate, not the multiplied group total.
    Flight/lodging fields are optional and cleared for unrelated categories.
    Flight times are local to each airport, so arrival is not compared with
    departure across time zones. save_expense validates the split separately.
    """
    name = name.strip()
    if not name:
        raise ValueError('Enter an expense name.')
    if len(name) > 80 or len(description) > 2000:
        raise ValueError('Limit expense name to 80 characters and description to 2,000.')
    cost_cents = parse_cost(cost)
    if category not in EXPENSE_CATEGORIES:
        raise ValueError('Choose an expense category.')
    if cost_basis not in ('group', 'per_person'):
        raise ValueError('Choose group total or per-person cost.')
    if split_mode not in ('everyone', 'selected', 'custom'):
        raise ValueError('Choose a split method.')
    if cost_status not in ('estimated', 'confirmed'):
        raise ValueError('Choose Estimated or Confirmed. This does not indicate payment.')
    details = dict(zip(EXPENSE_DETAILS, (expense_date, provider, airline, flight_number, departure_airport,
                                       arrival_airport, departure_at, arrival_at, check_in, check_out)))
    details = {key: value.strip() for key, value in details.items()}
    if any(len(value) > 160 for value in details.values()):
        raise ValueError('Keep expense details to 160 characters per field.')
    validate_optional_date(details['expense_date'], 'expense date')
    flight_fields = ('airline', 'flight_number', 'departure_airport', 'arrival_airport', 'departure_at', 'arrival_at')
    if category != 'Flights':
        for key in flight_fields:
            details[key] = ''
    else:
        for key in ('departure_at', 'arrival_at'):
            value = details[key]
            if value:
                try:
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', value):
                        raise ValueError()
                    datetime.strptime(value, '%Y-%m-%d %H:%M')
                except ValueError:
                    raise ValueError('Use flight date and time in YYYY-MM-DD HH:MM format (24-hour time).') from None
    if category != 'Lodging':
        details['check_in'] = details['check_out'] = ''
    else:
        validate_optional_date(details['check_in'], 'check-in date')
        validate_optional_date(details['check_out'], 'check-out date')
        if details['check_in'] and details['check_out'] and details['check_out'] < details['check_in']:
            raise ValueError('Check-out must be on or after check-in.')
    segments = json.loads(flight_segments) if isinstance(flight_segments, str) else (flight_segments or [])
    if not isinstance(segments, list) or len(segments) > 12:
        raise ValueError('Use up to 12 connecting flights per booking.')
    cleaned = []
    if category == 'Flights':
        for segment in segments:
            if not isinstance(segment, dict):
                raise ValueError('Each connecting flight must contain flight details.')
            fields = {key: str(segment.get(key, '')).strip() for key in flight_fields}
            if not any(fields.values()):
                continue
            # Reuse the same local date/time and length validation as the first flight.
            checked = validate_expense('Connection', '0', category='Flights', **fields)
            cleaned.append({key: checked[key] for key in flight_fields})
    return dict(name=name, cost_cents=cost_cents, description=description.strip(), cost_status=cost_status,
                flight_segments=json.dumps(cleaned), category=category, cost_basis=cost_basis, split_mode=split_mode, **details)


def is_past(trip, today=None):
    return bool(trip['end_date'] and trip['end_date'] < (today or date.today()).isoformat())


class TripStore:
    """Own the local database and all writes to trips, expenses, and travelers.

    Read methods return ordinary dictionaries (or None for missing IDs).
    Save methods expect validate_* output, and return the saved record's ID.
    Child records are always scoped to a trip to prevent cross-trip edits.
    """
    fields = ('name', 'destination', 'cost_cents', 'people', 'description', 'start_date', 'end_date', 'budget_set')
    expense_fields = ('name', 'cost_cents', 'description', 'category', 'cost_basis', 'split_mode', 'cost_status', 'flight_segments') + EXPENSE_DETAILS

    def __init__(self, path):
        """Create the database directory, tables, and missing columns on startup.

        Migrations are additive and run once per missing column. Defaults keep
        old records readable without resetting the user's saved trips.
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS trips (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, destination TEXT NOT NULL,
                cost_cents INTEGER NOT NULL CHECK(cost_cents >= 0),
                people INTEGER NOT NULL CHECK(people BETWEEN 1 AND 999),
                description TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY, trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                name TEXT NOT NULL, cost_cents INTEGER NOT NULL CHECK(cost_cents >= 0),
                description TEXT NOT NULL)''')
            db.execute('CREATE INDEX IF NOT EXISTS expenses_trip_id ON expenses(trip_id)')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(expenses)')}
            for column, default in [('category', 'Other'), ('cost_basis', 'group')] + [(key, '') for key in EXPENSE_DETAILS]:
                if column not in columns:
                    db.execute(f"ALTER TABLE expenses ADD COLUMN {column} TEXT NOT NULL DEFAULT '{default}'")
            for column, declaration in [('split_mode', "TEXT NOT NULL DEFAULT 'everyone'"),
                                         ('split_count', 'INTEGER NOT NULL DEFAULT 0'),
                                         ('split_review', 'INTEGER NOT NULL DEFAULT 0')]:
                if column not in columns:
                    db.execute(f'ALTER TABLE expenses ADD COLUMN {column} {declaration}')
            if 'split_count' not in columns:
                # Snapshot the old headcount so upgrading cannot change an
                # existing per-person expense total. Named shares need review.
                db.execute('''UPDATE expenses SET split_count=(SELECT people FROM trips WHERE trips.id=expenses.trip_id),
                              split_review=1''')
            db.execute('''CREATE TABLE IF NOT EXISTS travelers (
                id INTEGER PRIMARY KEY, trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                name TEXT NOT NULL, age INTEGER CHECK(age BETWEEN 0 AND 120), phone TEXT NOT NULL,
                email TEXT NOT NULL, gender TEXT NOT NULL, image_bytes BLOB)''')
            db.execute('CREATE INDEX IF NOT EXISTS travelers_trip_id ON travelers(trip_id)')
            db.execute('''CREATE TABLE IF NOT EXISTS expense_shares (
                expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
                traveler_id INTEGER REFERENCES travelers(id) ON DELETE SET NULL,
                traveler_name TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK(amount_cents>=0))''')
            db.execute('CREATE INDEX IF NOT EXISTS shares_expense_id ON expense_shares(expense_id)')
            trip_columns = {row['name'] for row in db.execute('PRAGMA table_info(trips)')}
            if 'budget_set' not in trip_columns:
                db.execute('ALTER TABLE trips ADD COLUMN budget_set INTEGER NOT NULL DEFAULT 1')
            for column, default in [('cost_status', 'estimated'), ('flight_segments', '[]')]:
                if column not in columns:
                    db.execute(f"ALTER TABLE expenses ADD COLUMN {column} TEXT NOT NULL DEFAULT '{default}'")
            for table in ('trips', 'expenses', 'travelers'):
                table_columns = {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
                if 'pending_delete' not in table_columns:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN pending_delete INTEGER NOT NULL DEFAULT 0')
            # Undo is session-only: unfinished deletions become permanent on reopen.
            db.execute('DELETE FROM trips WHERE pending_delete=1')
            db.execute('DELETE FROM expenses WHERE pending_delete=1')
            pending_ids = [r['id'] for r in db.execute('SELECT id FROM travelers WHERE pending_delete=1')]
            for tid in pending_ids:
                db.execute('UPDATE expenses SET split_review=1 WHERE id IN (SELECT expense_id FROM expense_shares WHERE traveler_id=?)', (tid,))
            db.execute('DELETE FROM travelers WHERE pending_delete=1')

    @contextmanager
    def connect(self):
        """Yield a transactional connection, then commit/roll back and close it.

        Foreign keys must be enabled on every connection. Deleting a trip or
        expense cascades to children; deleting a traveler preserves their share
        by setting traveler_id to NULL, keeping traveler_name as a snapshot.
        """
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def all(self):
        """Return all trips, newest-created first (by ID, not travel date)."""
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM trips WHERE pending_delete=0 ORDER BY id DESC')]

    def get(self, trip_id):
        """Return one trip dictionary, or None when it no longer exists."""
        with self.connect() as db:
            row = db.execute('SELECT * FROM trips WHERE id=? AND pending_delete=0', (trip_id,)).fetchone()
            return dict(row) if row else None

    def save(self, trip, trip_id=None, create_default_traveler=False):
        """Insert a validated trip, or update trip_id without changing saved splits."""
        values = [trip[f] for f in self.fields]
        with self.connect() as db:
            if trip_id is None:
                trip_id = db.execute('INSERT INTO trips (' + ','.join(self.fields) + ') VALUES (' + ','.join('?' for _ in values) + ')', values).lastrowid
                if create_default_traveler:
                    db.execute("INSERT INTO travelers (trip_id,name,age,phone,email,gender) VALUES (?, 'You', NULL, '', '', '')", (trip_id,))
                return trip_id
            cursor = db.execute('UPDATE trips SET ' + ','.join(f'{f}=?' for f in self.fields) + ' WHERE id=?', values + [trip_id])
            if cursor.rowcount != 1:
                raise ValueError('This trip no longer exists.')
            return trip_id

    def delete(self, trip_id):
        """Delete a trip and cascade-delete its expenses, profiles, and shares."""
        with self.connect() as db:
            db.execute('DELETE FROM trips WHERE id=?', (trip_id,))

    def expenses(self, trip_id):
        """Return this trip's expenses, including stored split/review metadata."""
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM expenses WHERE trip_id=? AND pending_delete=0 ORDER BY id DESC', (trip_id,))]

    def expense_total(self, trip_id):
        """Sum group totals using the same rate/count rule as expense_total_cents."""
        with self.connect() as db:
            return db.execute('''SELECT COALESCE(SUM(CASE WHEN e.cost_basis='per_person'
                THEN e.cost_cents*CASE WHEN e.split_count>0 THEN e.split_count ELSE t.people END ELSE e.cost_cents END), 0)
                FROM expenses e JOIN trips t ON t.id=e.trip_id WHERE e.trip_id=? AND e.pending_delete=0 AND t.pending_delete=0''', (trip_id,)).fetchone()[0]

    def get_expense(self, trip_id, expense_id):
        """Look up an expense only within its owning trip; return None if absent."""
        with self.connect() as db:
            row = db.execute('SELECT * FROM expenses WHERE trip_id=? AND id=? AND pending_delete=0', (trip_id, expense_id)).fetchone()
            return dict(row) if row else None

    def save_expense(self, trip_id, expense, expense_id=None, participant_ids=None, custom_amounts=None):
        """Save a validated expense and replace its shares in one transaction.

        An explicit save snapshots current participants and recalculates shares.
        Merely changing the trip/profile roster does not call this method.
        participant_ids contains checked profile IDs; custom_amounts maps those
        IDs to dollar strings and is used only by the custom split mode.
        Any validation/write failure rolls back the whole operation.
        """
        values = [expense[field] for field in self.expense_fields]
        with self.connect() as db:
            trip = db.execute('SELECT * FROM trips WHERE id=? AND pending_delete=0', (trip_id,)).fetchone()
            if not trip:
                raise ValueError('This trip no longer exists.')
            travelers = [dict(row) for row in db.execute('SELECT id,name FROM travelers WHERE trip_id=? AND pending_delete=0', (trip_id,))]
            count, shares = calculate_split(expense, trip['people'], travelers, participant_ids, custom_amounts)
            if expense_id is None:
                expense_id = db.execute('INSERT INTO expenses (' + ','.join(self.expense_fields) + ',trip_id) VALUES (' +
                                  ','.join('?' for _ in values) + ',?)', values + [trip_id]).lastrowid
            else:
                cursor = db.execute('UPDATE expenses SET ' + ','.join(f'{field}=?' for field in self.expense_fields) + ' WHERE trip_id=? AND id=?',
                                    values + [trip_id, expense_id])
                if cursor.rowcount != 1:
                    raise ValueError('This expense no longer exists.')
            db.execute('UPDATE expenses SET split_count=?,split_review=? WHERE id=?', (count, not bool(shares), expense_id))
            # Replace, rather than append, so changing a split cannot leave stale
            # allocations attached to the expense. Both writes commit together.
            db.execute('DELETE FROM expense_shares WHERE expense_id=?', (expense_id,))
            names = {traveler['id']: traveler['name'] for traveler in travelers}
            db.executemany('INSERT INTO expense_shares VALUES (?,?,?,?)',
                           [(expense_id, tid, names[tid], cents) for tid, cents in shares.items()])
            return expense_id

    def expense_shares(self, trip_id, expense_id):
        """Return named allocations, including snapshots of removed travelers.

        name uses the current profile name when present, otherwise the saved
        traveler_name. A NULL traveler_id means the profile was deleted.
        """
        with self.connect() as db:
            return [dict(row) for row in db.execute('''SELECT s.expense_id,
                CASE WHEN t.id IS NULL THEN NULL ELSE s.traveler_id END AS traveler_id,
                s.traveler_name,s.amount_cents,COALESCE(t.name,s.traveler_name) AS name
                FROM expense_shares s JOIN expenses e ON e.id=s.expense_id LEFT JOIN travelers t ON t.id=s.traveler_id AND t.pending_delete=0
                WHERE e.trip_id=? AND e.id=? ORDER BY s.traveler_id,s.traveler_name''', (trip_id, expense_id))]

    def traveler_shares(self, trip_id, traveler_id):
        """Return an active traveler's expense breakdown; sum amount_cents for total."""
        with self.connect() as db:
            return [dict(row) for row in db.execute('''SELECT e.id,e.name,e.category,e.split_review,s.amount_cents
                FROM expense_shares s JOIN expenses e ON e.id=s.expense_id JOIN travelers t ON t.id=s.traveler_id
                WHERE e.trip_id=? AND t.trip_id=? AND s.traveler_id=? AND e.pending_delete=0 AND t.pending_delete=0 ORDER BY e.id DESC''', (trip_id, trip_id, traveler_id))]

    def delete_expense(self, trip_id, expense_id):
        """Delete this trip's expense and its allocations via foreign-key cascade."""
        with self.connect() as db:
            db.execute('DELETE FROM expenses WHERE trip_id=? AND id=?', (trip_id, expense_id))

    def travelers(self, trip_id):
        """Return this trip's profiles, including optional photo bytes."""
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM travelers WHERE trip_id=? AND pending_delete=0 ORDER BY id DESC', (trip_id,))]

    def get_traveler(self, trip_id, traveler_id):
        """Return a profile only if it belongs to the requested trip."""
        with self.connect() as db:
            row = db.execute('SELECT * FROM travelers WHERE trip_id=? AND id=? AND pending_delete=0', (trip_id, traveler_id)).fetchone()
            return dict(row) if row else None

    def save_traveler(self, trip_id, traveler, traveler_id=None):
        """Save a profile/photo; additions flag Everyone expenses for review.

        Renaming updates the stored share names without altering their amounts.
        Adding a profile does not increase the trip's planned headcount.
        """
        fields = ('name', 'age', 'phone', 'email', 'gender', 'image_bytes')
        values = [traveler[field] for field in fields]
        with self.connect() as db:
            if not db.execute('SELECT id FROM trips WHERE id=?', (trip_id,)).fetchone():
                raise ValueError('This trip no longer exists.')
            if traveler_id is None:
                traveler_id = db.execute('INSERT INTO travelers (' + ','.join(fields) + ',trip_id) VALUES (?,?,?,?,?,?,?)',
                                         values + [trip_id]).lastrowid
                db.execute("UPDATE expenses SET split_review=1 WHERE trip_id=? AND split_mode='everyone'", (trip_id,))
                return traveler_id
            cursor = db.execute('UPDATE travelers SET ' + ','.join(f'{f}=?' for f in fields) + ' WHERE trip_id=? AND id=?',
                                values + [trip_id, traveler_id])
            if cursor.rowcount != 1:
                raise ValueError('This traveler no longer exists.')
            db.execute('UPDATE expense_shares SET traveler_name=? WHERE traveler_id=?', (traveler['name'], traveler_id))
            return traveler_id

    def delete_traveler(self, trip_id, traveler_id):
        """Remove the profile/photo, flag affected expenses, and retain named shares.

        The foreign key sets the share's traveler_id to NULL; its saved name
        and amount remain until the user explicitly reviews that expense.
        """
        with self.connect() as db:
            db.execute('''UPDATE expenses SET split_review=1 WHERE trip_id=? AND id IN
                (SELECT expense_id FROM expense_shares WHERE traveler_id=?)''', (trip_id, traveler_id))
            db.execute('DELETE FROM travelers WHERE trip_id=? AND id=?', (trip_id, traveler_id))
