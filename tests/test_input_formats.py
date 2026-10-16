import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trip_store import parse_cost, display_date, validate_trip, validate_expense, calculate_split


class InputFormatTests(unittest.TestCase):
    def test_comma_costs_across_forms(self):
        self.assertEqual(parse_cost(' 1,250.99 '), 125099)
        self.assertEqual(parse_cost('1,000,000'), 100000000)
        self.assertEqual(validate_trip('Trip', 'Boston', '1,250.00', '2')['cost_cents'], 125000)
        expense = validate_expense('Hotel', '2,500.00', split_mode='custom')
        _, shares = calculate_split(expense, 2, [{'id': 1}, {'id': 2}], [1, 2], {1: '1,500.00', 2: '1,000.00'})
        self.assertEqual(shares, {1: 150000, 2: 100000})

    def test_invalid_comma_grouping(self):
        for value in ('1,25', '12,50.00', ',100', '1,000,', '1,,000', '1,000.001', '-1,000', '1,000,000,000', '1.250,00'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_cost(value)

    def test_friendly_display_leaves_canonical_values_unchanged(self):
        self.assertEqual(display_date('2020-01-12'), 'Jan 12, 2020')
        self.assertEqual(display_date('2024-02-29'), 'Feb 29, 2024')
        self.assertEqual(display_date('2020-01-12 08:30'), 'Jan 12, 2020 at 08:30')
        self.assertEqual(display_date(''), 'Not set')
        trip = validate_trip('Trip', 'Boston', '1,250', '2', start_date='2020-01-12', end_date='2020-01-15')
        self.assertEqual(trip['start_date'], '2020-01-12')


if __name__ == '__main__':
    unittest.main()
