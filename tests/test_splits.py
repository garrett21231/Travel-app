import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trip_store import TripStore, validate_trip, validate_traveler, validate_expense, calculate_split


class SplitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = TripStore(Path(self.temp.name) / 'trips.sqlite3')
        self.trip_id = self.store.save(validate_trip('Trip', 'Boston', '2000', '4'))
        self.ids = [self.store.save_traveler(self.trip_id, validate_traveler(name)) for name in ('Alex', 'Sam', 'Jo', 'Pat')]

    def tearDown(self):
        self.temp.cleanup()

    def test_flight_everyone_hotel_selected_example(self):
        flight = self.store.save_expense(self.trip_id, validate_expense('Flights', '200', cost_basis='per_person'))
        hotel = self.store.save_expense(self.trip_id, validate_expense('Hotel', '600', split_mode='selected'), participant_ids=self.ids[:2])
        self.assertEqual(self.store.expense_total(self.trip_id), 140000)
        self.assertEqual(len(self.store.expense_shares(self.trip_id, flight)), 4)
        self.assertEqual(len(self.store.expense_shares(self.trip_id, hotel)), 2)
        totals = [sum(s['amount_cents'] for s in self.store.traveler_shares(self.trip_id, tid)) for tid in self.ids]
        self.assertEqual(totals, [50000, 50000, 20000, 20000])
        self.assertEqual(sum(totals), self.store.expense_total(self.trip_id))
        self.assertEqual(TripStore(self.store.path).expense_total(self.trip_id), 140000)

    def test_selected_per_person_and_rounding(self):
        expense = validate_expense('Dinner', '10.01', split_mode='selected')
        eid = self.store.save_expense(self.trip_id, expense, participant_ids=self.ids[:3])
        amounts = [s['amount_cents'] for s in self.store.expense_shares(self.trip_id, eid)]
        self.assertEqual(amounts, [334, 334, 333])
        self.assertEqual(sum(amounts), 1001)
        per_person = validate_expense('Taxi', '12.35', cost_basis='per_person', split_mode='selected')
        self.store.save_expense(self.trip_id, per_person, eid, participant_ids=self.ids[:2])
        self.assertEqual(self.store.expense_total(self.trip_id), 2470)

    def test_custom_amounts_and_atomic_validation(self):
        expense = validate_expense('Dinner', '100', split_mode='custom')
        eid = self.store.save_expense(self.trip_id, expense, participant_ids=self.ids[:3],
                                      custom_amounts=dict(zip(self.ids[:3], ('70', '30', '0'))))
        self.assertEqual([s['amount_cents'] for s in self.store.expense_shares(self.trip_id, eid)], [7000, 3000, 0])
        for amounts in ({self.ids[0]: '50', self.ids[1]: '40'}, {self.ids[0]: '-1', self.ids[1]: '101'},
                        {self.ids[0]: '100.001', self.ids[1]: '0'}):
            with self.assertRaises(ValueError):
                self.store.save_expense(self.trip_id, expense, eid, self.ids[:2], amounts)
            self.assertEqual(self.store.expense_total(self.trip_id), 10000)
            self.assertEqual(len(self.store.expense_shares(self.trip_id, eid)), 3)

    def test_add_remove_keeps_saved_shares_and_flags_review(self):
        expense = validate_expense('Flight', '200', cost_basis='per_person')
        eid = self.store.save_expense(self.trip_id, expense)
        before = self.store.expense_shares(self.trip_id, eid)
        added = self.store.save_traveler(self.trip_id, validate_traveler('New traveler'))
        self.assertEqual(self.store.expense_shares(self.trip_id, eid), before)
        self.assertEqual(self.store.expense_total(self.trip_id), 80000)
        self.assertTrue(self.store.get_expense(self.trip_id, eid)['split_review'])
        self.assertEqual(self.store.traveler_shares(self.trip_id, added), [])
        self.store.delete_traveler(self.trip_id, self.ids[0])
        shares = self.store.expense_shares(self.trip_id, eid)
        self.assertEqual(sum(s['amount_cents'] for s in shares), 80000)
        removed = next(s for s in shares if s['traveler_id'] is None)
        self.assertEqual(removed['name'], 'Alex')
        self.store.save_expense(self.trip_id, expense, eid)
        self.assertFalse(self.store.get_expense(self.trip_id, eid)['split_review'])
        self.assertTrue(all(s['traveler_id'] is not None for s in self.store.expense_shares(self.trip_id, eid)))
        self.store.delete(self.trip_id)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM expense_shares').fetchone()[0], 0)

    def test_trip_isolation_and_no_empty_selected_split(self):
        other = self.store.save(validate_trip('Other', 'Paris', '1', '1'))
        outsider = self.store.save_traveler(other, validate_traveler('Outsider'))
        expense = validate_expense('Hotel', '10', split_mode='selected')
        for ids in ([], [outsider], [self.ids[0], self.ids[0]]):
            with self.assertRaises(ValueError):
                self.store.save_expense(self.trip_id, expense, participant_ids=ids)
        self.assertEqual(self.store.expenses(self.trip_id), [])

    def test_no_profiles_keeps_total_unassigned(self):
        other = self.store.save(validate_trip('Other', 'Paris', '1', '3'))
        eid = self.store.save_expense(other, validate_expense('Flight', '200', cost_basis='per_person'))
        self.assertEqual(self.store.expense_total(other), 60000)
        self.assertEqual(self.store.expense_shares(other, eid), [])
        self.assertTrue(self.store.get_expense(other, eid)['split_review'])
        self.store.save(validate_trip('Other', 'Paris', '1', '4'), other)
        self.assertEqual(self.store.expense_total(other), 60000)


if __name__ == '__main__':
    unittest.main()
