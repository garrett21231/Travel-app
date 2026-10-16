import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trip_store import TripStore, validate_trip, validate_expense, validate_traveler
from planning_tools import backup_text, import_backup, duplicate_trip, trip_summary, stage_delete, stage_trip_deletions, finish_delete


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = TripStore(Path(self.folder.name) / 'trips.sqlite3')

    def tearDown(self):
        self.folder.cleanup()

    def example(self):
        tid = self.store.save(validate_trip('Snowboarding', 'Resort\nBoston', '1000', '2', 'Compare rental prices', '2027-01-12', '2027-01-15'))
        you = self.store.save_traveler(tid, validate_traveler('You', email='you@example.com', image_bytes=(Path(__file__).parents[1] / 'assets' / 'field.png').read_bytes()))
        friend = self.store.save_traveler(tid, validate_traveler('Friend'))
        hotel = self.store.save_expense(tid, validate_expense('Hotel', '600', category='Lodging', cost_status='confirmed'))
        ski = self.store.save_expense(tid, validate_expense('Ski pass', '250', split_mode='selected'), participant_ids=[you])
        return tid, you, friend, hotel, ski

    def test_name_only_budget_zero_and_default_profile(self):
        trip = validate_trip('Idea')
        tid = self.store.save(trip, create_default_traveler=True)
        self.assertEqual(trip['budget_set'], 0)
        self.assertEqual(trip['destination'], '')
        self.assertEqual(validate_trip('Idea', people='')['people'], 1)
        self.assertEqual(self.store.travelers(tid)[0]['name'], 'You')
        self.store.save(validate_trip('Idea', cost='0'), tid)
        self.assertEqual(self.store.get(tid)['budget_set'], 1)

    def test_budget_is_separate_and_status_does_not_change_sum(self):
        tid, you, friend, hotel, ski = self.example()
        self.assertEqual(self.store.expense_total(tid), 85000)
        self.assertEqual(self.store.get(tid)['cost_cents'], 100000)
        self.assertEqual(self.store.get_expense(tid, hotel)['cost_status'], 'confirmed')
        self.store.save(validate_trip('Trip', cost='1200', people='2'), tid)
        self.assertEqual(self.store.expense_total(tid), 85000)

    def test_connections_cost_counted_once(self):
        tid = self.store.save(validate_trip('Flights'))
        expense = validate_expense('Booking', '450', category='Flights', flight_number='AA1',
                                   flight_segments=[dict(departure_airport='London', arrival_airport='Rome', flight_number='AA2', departure_at='2027-01-13 10:00')])
        eid = self.store.save_expense(tid, expense)
        self.assertEqual(self.store.expense_total(tid), 45000)
        self.assertEqual(json.loads(self.store.get_expense(tid, eid)['flight_segments'])[0]['flight_number'], 'AA2')
        with self.assertRaises(ValueError):
            validate_expense('Booking', '1', category='Flights', flight_segments=[dict(departure_at='yesterday')])

    def test_backup_roundtrip_remaps_ids_and_keeps_images_splits(self):
        tid, you, friend, hotel, ski = self.example()
        copies = import_backup(self.store, backup_text(self.store, [tid]))
        new = copies[0]
        self.assertNotEqual(new, tid)
        self.assertEqual(self.store.expense_total(new), 85000)
        profiles = self.store.travelers(new)
        copied_you = next(t for t in profiles if t['name'] == 'You')
        self.assertNotEqual(copied_you['id'], you)
        self.assertTrue(copied_you['image_bytes'])
        self.assertEqual(sum(s['amount_cents'] for s in self.store.traveler_shares(new, copied_you['id'])), 55000)
        self.store.delete(tid)
        self.assertEqual(self.store.expense_total(new), 85000)

    def test_import_validation_is_atomic(self):
        tid, *_ = self.example()
        data = json.loads(backup_text(self.store, [tid]))
        data['trips'].append(dict(data['trips'][0], trip=dict(data['trips'][0]['trip'], name=' ')))
        with self.assertRaises(ValueError):
            import_backup(self.store, json.dumps(data))
        self.assertEqual(len(self.store.all()), 1)
        data = json.loads(backup_text(self.store, [tid]))
        data['trips'][0]['expenses'][0]['shares'][0]['amount_cents'] += 1
        with self.assertRaises(ValueError):
            import_backup(self.store, json.dumps(data))
        self.assertEqual(len(self.store.all()), 1)
        with self.assertRaises(ValueError):
            import_backup(self.store, 'not json')

    def test_duplicate_options_and_independence(self):
        tid, *_ = self.example()
        new = duplicate_trip(self.store, tid, clear_dates=True, reset_confirmed=True)
        self.assertEqual(self.store.get(new)['start_date'], '')
        self.assertEqual(self.store.get(new)['destination'], 'Resort\nBoston')
        self.assertTrue(all(e['cost_status'] == 'estimated' for e in self.store.expenses(new)))
        self.store.save(validate_trip('Changed'), new)
        self.assertEqual(self.store.get(tid)['name'], 'Snowboarding')

    def test_summary_is_readable_and_excludes_contact_details(self):
        tid, *_ = self.example()
        document = trip_summary(self.store, tid)
        self.assertIn('$850.00', document)
        self.assertIn('You: $550.00', document)
        self.assertIn('Friend: $300.00', document)
        self.assertIn('confirmed', document)
        self.assertNotIn('you@example.com', document)

    def test_expense_undo_preserves_ids_and_allocations(self):
        tid, you, friend, hotel, ski = self.example()
        before = self.store.expense_shares(tid, hotel)
        token = stage_delete(self.store, 'expenses', hotel)
        self.assertEqual(self.store.expense_total(tid), 25000)
        self.assertIsNone(self.store.get_expense(tid, hotel))
        self.assertEqual(sum(s['amount_cents'] for s in self.store.traveler_shares(tid, you)), 25000)
        finish_delete(self.store, token, undo=True)
        self.assertEqual(self.store.expense_total(tid), 85000)
        self.assertEqual(self.store.expense_shares(tid, hotel), before)

    def test_traveler_and_trip_undo_and_expiration(self):
        tid, you, friend, hotel, ski = self.example()
        token = stage_delete(self.store, 'travelers', you)
        self.assertEqual(len(self.store.travelers(tid)), 1)
        self.assertEqual(self.store.expense_total(tid), 85000)
        self.assertTrue(any(s['traveler_id'] is None for s in self.store.expense_shares(tid, hotel)))
        self.assertTrue(self.store.get_expense(tid, hotel)['split_review'])
        finish_delete(self.store, token, undo=True)
        self.assertEqual(len(self.store.travelers(tid)), 2)
        self.assertFalse(self.store.get_expense(tid, hotel)['split_review'])
        token = stage_delete(self.store, 'trips', tid)
        self.assertEqual(self.store.all(), [])
        finish_delete(self.store, token, undo=True)
        self.assertEqual(self.store.expense_total(tid), 85000)
        token = stage_delete(self.store, 'travelers', you)
        finish_delete(self.store, token)
        self.assertIsNone(self.store.get_traveler(tid, you))
        self.assertTrue(self.store.get_expense(tid, hotel)['split_review'])

    def test_reopen_finalizes_unfinished_deletion(self):
        tid, *_ = self.example()
        stage_delete(self.store, 'trips', tid)
        reopened = TripStore(self.store.path)
        self.assertEqual(reopened.all(), [])
        with reopened.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM expense_shares').fetchone()[0], 0)

    def test_group_delete_undo_restores_all_details_and_leaves_others(self):
        tid, *_ = self.example()
        other = duplicate_trip(self.store, tid)
        keep = self.store.save(validate_trip('Keep this trip'))
        original = backup_text(self.store)
        token = stage_trip_deletions(self.store, [tid, other, tid])
        self.assertEqual([t['id'] for t in self.store.all()], [keep])
        self.assertEqual(len(token['ids']), 2)
        finish_delete(self.store, token, undo=True)
        self.assertEqual(backup_text(self.store), original)

    def test_group_delete_expiration_cascades_only_selected_trips(self):
        tid, *_ = self.example()
        other = duplicate_trip(self.store, tid)
        keep = duplicate_trip(self.store, tid)
        expected = backup_text(self.store, [keep])
        finish_delete(self.store, stage_trip_deletions(self.store, [tid, other]))
        self.assertEqual(backup_text(self.store), expected)
        with self.store.connect() as db:
            for table in ('expenses', 'travelers'):
                self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table} WHERE trip_id IN (?,?)', (tid, other)).fetchone()[0], 0)
            expected_shares = sum(len(self.store.expense_shares(keep, expense['id'])) for expense in self.store.expenses(keep))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM expense_shares').fetchone()[0], expected_shares)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_group_delete_rejects_invalid_selection_without_hiding_anything(self):
        tid, *_ = self.example()
        original = backup_text(self.store)
        for ids in ([], [tid, tid + 1000]):
            with self.assertRaises(ValueError):
                stage_trip_deletions(self.store, ids)
            self.assertEqual(backup_text(self.store), original)

    def test_group_delete_reopen_finalizes_whole_group(self):
        tid, *_ = self.example()
        other = duplicate_trip(self.store, tid)
        keep = self.store.save(validate_trip('Keep'))
        stage_trip_deletions(self.store, [tid, other])
        reopened = TripStore(self.store.path)
        self.assertEqual([t['id'] for t in reopened.all()], [keep])
        with reopened.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM expenses').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM travelers').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM expense_shares').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
