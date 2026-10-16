import sys
from pathlib import Path
import tempfile
import unittest
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trip_store import (TripStore, validate_trip, validate_expense, validate_traveler,
                        MAX_PHOTO_BYTES, money, is_past, expense_total_cents)


class TripTests(unittest.TestCase):
    def test_persistence_edit_and_delete(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'trips.sqlite3'
            trip = validate_trip(" Friend's trip ", ' Montréal ', '1200.99', '3', 'Bring snacks')
            trip_id = TripStore(path).save(trip)
            reopened = TripStore(path)
            stored = reopened.get(trip_id)
            self.assertEqual(stored['name'], "Friend's trip")
            self.assertEqual(stored['destination'], 'Montréal')
            self.assertEqual(stored['cost_cents'], 120099)
            self.assertEqual(stored['description'], 'Bring snacks')
            edited = validate_trip('Revised trip', 'Boston', '99.95', '2')
            reopened.save(edited, trip_id)
            self.assertEqual(TripStore(path).get(trip_id)['cost_cents'], 9995)
            reopened.delete(trip_id)
            self.assertEqual(TripStore(path).all(), [])

    def test_money_rounding(self):
        self.assertEqual(money(1000, 3), '$3.33')
        self.assertEqual(money(1, 2), '$0.01')
        self.assertEqual(money(120099), '$1,200.99')

    def test_invalid_inputs(self):
        for cost in ('-1', 'NaN', 'Infinity', '1.001', '1e3', '1000000000', 'abc'):
            with self.subTest(cost=cost), self.assertRaises(ValueError):
                validate_trip('Trip', 'Place', cost, '2')
        for people in ('0', '-1', '1.5', '1000'):
            with self.subTest(people=people), self.assertRaises(ValueError):
                validate_trip('Trip', 'Place', '1', people)
        for name, place in ((' ', 'Paris'),):
            with self.assertRaises(ValueError):
                validate_trip(name, place, '1', '1')
        self.assertEqual(validate_trip('Trip', 'Place', '0', '1')['cost_cents'], 0)

    def test_dates_and_past_filter(self):
        for start, end in (('2026-02-30', '2026-03-01'), ('2026-10-12', '2026-10-11'), ('2026-10-11', ''), ('2026-1-1', '2026-01-02')):
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                validate_trip('Trip', 'Place', '1', '2', start_date=start, end_date=end)
        today = date(2026, 10, 11)
        self.assertTrue(is_past({'end_date': '2026-10-10'}, today))
        self.assertFalse(is_past({'end_date': '2026-10-11'}, today))
        self.assertFalse(is_past({'end_date': ''}, today))

    def test_expense_persistence_totals_and_trip_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'trips.sqlite3'
            store = TripStore(path)
            trip = validate_trip('Boston', 'Boston', '1000', '2')
            first, second = store.save(trip), store.save(trip)
            flight = store.save_expense(first, validate_expense(' Plane flight ', '350.99', 'Round trip'))
            hotel = store.save_expense(first, validate_expense('Hotel', '400'))
            store.save_expense(second, validate_expense('Train', '30'))
            reopened = TripStore(path)
            self.assertEqual(reopened.expense_total(first), 75099)
            self.assertEqual(reopened.expense_total(second), 3000)
            self.assertEqual(reopened.get_expense(first, flight)['description'], 'Round trip')
            self.assertEqual(reopened.get(first)['cost_cents'], 100000)
            self.assertIsNone(reopened.get_expense(second, flight))
            with self.assertRaises(ValueError):
                reopened.save_expense(second, validate_expense('Wrong trip', '1'), flight)
            reopened.delete_expense(second, flight)
            self.assertIsNotNone(reopened.get_expense(first, flight))
            reopened.save_expense(first, validate_expense('Flight', '300'), flight)
            self.assertEqual(reopened.expense_total(first), 70000)
            reopened.delete_expense(first, hotel)
            self.assertEqual(reopened.expense_total(first), 30000)
            reopened.delete(first)
            self.assertEqual(reopened.expenses(first), [])
            self.assertEqual(reopened.expense_total(first), 0)
            self.assertEqual(len(reopened.expenses(second)), 1)
            with self.assertRaises(ValueError):
                reopened.save_expense(first, validate_expense('Orphan', '1'))

    def test_existing_database_upgrade(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'old.sqlite3'
            with sqlite3.connect(path) as db:
                db.execute('''CREATE TABLE trips (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                    destination TEXT NOT NULL, cost_cents INTEGER NOT NULL, people INTEGER NOT NULL,
                    description TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL)''')
                db.execute("INSERT INTO trips VALUES (1, 'Old trip', 'Boston', 10000, 2, '', '', '')")
            db.close()
            store = TripStore(path)
            self.assertEqual(store.get(1)['name'], 'Old trip')
            self.assertEqual(store.expenses(1), [])
            store.save_expense(1, validate_expense('Flight', '25'))
            self.assertEqual(TripStore(path).expense_total(1), 2500)
            store.save_traveler(1, validate_traveler('Alex'))
            self.assertEqual(TripStore(path).travelers(1)[0]['name'], 'Alex')
            self.assertEqual(store.get(1)['name'], 'Old trip')

    def test_expense_validation(self):
        for name, cost in [('', '1'), ('   ', '1'), ('Flight', ''), ('Flight', '-1'), ('Flight', 'NaN'),
                           ('Flight', '1.005'), ('Flight', '1e3'), ('x' * 81, '1')]:
            with self.subTest(name=name, cost=cost), self.assertRaises(ValueError):
                validate_expense(name, cost)
        self.assertEqual(validate_expense(' Free activity ', '0')['cost_cents'], 0)
        with self.assertRaises(ValueError):
            validate_expense('Flight', '1', 'x' * 2001)

    def test_rich_expense_details_and_saved_headcount_total(self):
        with tempfile.TemporaryDirectory() as folder:
            store = TripStore(Path(folder) / 'trips.sqlite3')
            trip_id = store.save(validate_trip('Boston', 'Boston', '1000', '3'))
            flight = validate_expense('Flight', '120.99', 'Carry-on included', category='Flights', cost_basis='per_person',
                                      expense_date='2027-06-12', provider='Airline booking', airline='Example Air', flight_number='EX123',
                                      departure_airport='LAX', arrival_airport='BOS', departure_at='2027-06-12 08:30', arrival_at='2027-06-12 17:00')
            fid = store.save_expense(trip_id, flight)
            lodge = validate_expense('Hotel', '200', category='Lodging', provider='Boston Hotel',
                                     check_in='2027-06-12', check_out='2027-06-15')
            store.save_expense(trip_id, lodge)
            reopened = TripStore(store.path)
            for key, value in flight.items():
                self.assertEqual(reopened.get_expense(trip_id, fid)[key], value)
            self.assertEqual(expense_total_cents(flight, 3), 36297)
            self.assertEqual(reopened.expense_total(trip_id), 56297)
            reopened.save(validate_trip('Boston', 'Boston', '1000', '4'), trip_id)
            self.assertEqual(reopened.expense_total(trip_id), 56297)
            reopened.save_expense(trip_id, flight, fid)  # Explicitly review the saved headcount.
            self.assertEqual(reopened.expense_total(trip_id), 68396)
            self.assertEqual(reopened.get_expense(trip_id, fid)['cost_cents'], 12099)
            reopened.save_expense(trip_id, validate_expense('Taxi', '25.50', category='Transportation'), fid)
            saved = reopened.get_expense(trip_id, fid)
            self.assertEqual(saved['airline'], '')
            self.assertEqual(saved['cost_basis'], 'group')
            self.assertEqual(reopened.expense_total(trip_id), 22550)

    def test_expense_category_date_validation(self):
        for details in [dict(category='Unknown'), dict(cost_basis='daily'), dict(expense_date='2027-02-30'),
                        dict(category='Flights', departure_at='2027-06-12 25:30'),
                        dict(category='Lodging', check_in='2027-06-15', check_out='2027-06-12'),
                        dict(provider='x' * 161)]:
            with self.subTest(details=details), self.assertRaises(ValueError):
                validate_expense('Expense', '10', **details)
        self.assertEqual(validate_expense('Dinner', '10', category='Food & drink', airline='unused')['airline'], '')
        # Flights use each airport's local time, so crossing time zones may look earlier.
        validate_expense('Flight', '10', category='Flights', departure_at='2027-06-12 18:00', arrival_at='2027-06-12 16:00')

    def test_old_expense_upgrade_preserves_amounts(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'legacy.sqlite3'
            with sqlite3.connect(path) as db:
                db.execute('''CREATE TABLE trips (id INTEGER PRIMARY KEY, name TEXT NOT NULL, destination TEXT NOT NULL,
                    cost_cents INTEGER NOT NULL, people INTEGER NOT NULL, description TEXT NOT NULL,
                    start_date TEXT NOT NULL, end_date TEXT NOT NULL)''')
                db.execute("INSERT INTO trips VALUES (1, 'Old trip', 'Boston', 10000, 3, '', '', '')")
                db.execute('''CREATE TABLE expenses (id INTEGER PRIMARY KEY, trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, cost_cents INTEGER NOT NULL, description TEXT NOT NULL)''')
                db.execute("INSERT INTO expenses VALUES (1, 1, 'Old flight', 35099, 'Original notes')")
            db.close()
            store = TripStore(path)
            saved = store.get_expense(1, 1)
            self.assertEqual(saved['category'], 'Other')
            self.assertEqual(saved['cost_basis'], 'group')
            self.assertEqual(saved['description'], 'Original notes')
            self.assertEqual(store.expense_total(1), 35099)
            self.assertEqual(TripStore(path).expense_total(1), 35099)

    def test_traveler_persistence_isolation_and_photo_removal(self):
        with tempfile.TemporaryDirectory() as folder:
            store = TripStore(Path(folder) / 'trips.sqlite3')
            trip = validate_trip('Trip', 'Boston', '100', '2')
            first, second = store.save(trip), store.save(trip)
            photo = (Path(__file__).resolve().parents[1] / 'assets' / 'field.png').read_bytes()
            traveler = validate_traveler(' Alex ', '25', '+1 (555) 123-4567', 'alex@example.com', 'Nonbinary', photo)
            tid = store.save_traveler(first, traveler)
            reopened = TripStore(store.path)
            saved = reopened.get_traveler(first, tid)
            self.assertEqual(saved['name'], 'Alex')
            self.assertEqual(saved['age'], 25)
            self.assertEqual(saved['phone'], '+1 (555) 123-4567')
            self.assertEqual(saved['email'], 'alex@example.com')
            self.assertEqual(saved['gender'], 'Nonbinary')
            self.assertEqual(saved['image_bytes'], photo)
            self.assertEqual(reopened.travelers(second), [])
            self.assertIsNone(reopened.get_traveler(second, tid))
            with self.assertRaises(ValueError):
                reopened.save_traveler(second, traveler, tid)
            reopened.delete_traveler(second, tid)
            self.assertIsNotNone(reopened.get_traveler(first, tid))
            reopened.save_traveler(first, validate_traveler('Alex', '26'), tid)
            self.assertIsNone(reopened.get_traveler(first, tid)['image_bytes'])
            self.assertEqual(reopened.get(first)['people'], 2)
            reopened.delete_traveler(first, tid)
            self.assertEqual(reopened.travelers(first), [])
            reopened.save_traveler(first, traveler)
            reopened.delete(first)
            self.assertEqual(reopened.travelers(first), [])
            with self.assertRaises(ValueError):
                reopened.save_traveler(first, traveler)

    def test_traveler_validation(self):
        self.assertIsNone(validate_traveler('Alex')['age'])
        self.assertEqual(validate_traveler('Infant', '0')['age'], 0)
        for fields in [dict(name=''), dict(name='x' * 81), dict(name='Alex', age='-1'),
                       dict(name='Alex', age='121'), dict(name='Alex', age='2.5'),
                       dict(name='Alex', email='not-an-email'), dict(name='Alex', phone='abc'),
                       dict(name='Alex', image_bytes=b'not an image'),
                       dict(name='Alex', image_bytes=b'x' * (MAX_PHOTO_BYTES + 1))]:
            with self.subTest(fields={k: str(v)[:30] for k, v in fields.items()}), self.assertRaises(ValueError):
                validate_traveler(**fields)


if __name__ == '__main__':
    unittest.main()
