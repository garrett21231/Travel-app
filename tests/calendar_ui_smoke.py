"""Verify calendar selection/cancellation, flight times, comma costs, and cards."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kivy.clock import Clock
from kivy.uix.button import Button
from main import TripPlannerApp, Action
from date_picker import DateField

OUTPUT = Path(__file__).parent / 'artifacts'
OUTPUT.mkdir(exist_ok=True)


class CalendarSmoke(TripPlannerApp):
    def on_start(self):
        self.failures = []
        self.steps = iter([self.trip_start, self.trip_calendar, self.trip_save, self.expense_start,
                           self.expense_calendar, self.expense_save, self.flight_start, self.flight_calendar,
                           self.flight_save, self.lodging_calendar, self.finished])
        Clock.schedule_once(self.step, .5)

    def step(self, _):
        try:
            next(self.steps)()
        except StopIteration:
            self.stop()
            return
        except Exception as error:
            self.failures.append(error)
            self.stop()
            return
        Clock.schedule_once(self.step, .5)

    def press(self, caption, root=None):
        next(w for w in (root or self.root).walk() if isinstance(w, Button) and w.text == caption).dispatch('on_release')

    def capture(self, name):
        self.root.export_as_image().save(str(OUTPUT / f'{name}.png'))

    def select(self, field, year, month, day):
        field.open_calendar()
        field.year_choice.text = str(year)
        field.month_choice.text = month
        self.press(str(day), field.days)

    def trip_start(self):
        self.show_form()
        self.inputs['name'].text = 'Boston getaway'
        self.inputs['destination'].text = 'Boston'
        self.inputs['cost'].text = '1,250.00'
        self.inputs['people'].text = '2'
        assert '$625.00' in self.preview.text
        field = self.inputs['start_date']
        assert isinstance(field, DateField)

    def trip_calendar(self):
        field = self.inputs['start_date']
        field.date_button.dispatch('on_release')
        field.year_choice.text = '2020'
        field.month_choice.text = 'Jan'
        self.menu_for_capture = field.calendar_menu
        # Give the menu itself a rendering frame before inspecting the popup.
        Clock.schedule_once(lambda _: self.menu_for_capture.export_as_image().save(str(OUTPUT / 'calendar-popup.png')), .1)
        self.capture('trip-calendar-menu')
        self.press('12', self.inputs['start_date'].days)
        assert self.inputs['start_date'].text == '2020-01-12'
        assert self.inputs['start_date'].date_button.text == 'Jan 12, 2020'
        self.select(self.inputs['end_date'], 2020, 'Jan', 15)
        field = self.inputs['start_date']
        field.open_calendar()
        field.move_month(1)
        self.press('Cancel', field.calendar_menu)
        assert field.text == '2020-01-12'

    def trip_save(self):
        self.press('Save trip')
        assert self.page == 'detail'
        assert self.store.get(self.trip_id)['cost_cents'] == 125000
        assert any(getattr(w, 'text', '') == 'Jan 12, 2020 – Jan 15, 2020' for w in self.root.walk())
        self.show_detail(self.trip_id, 'expenses')
        self.press('+ New expense')

    def expense_start(self):
        self.expense_inputs['name'].text = 'Dinner with friends'
        self.expense_inputs['cost'].text = '2,500.00'
        self.expense_inputs['provider'].text = 'Boston restaurant'
        self.expense_category.text = 'Food & drink'
        self.select(self.expense_inputs['expense_date'], 2024, 'Feb', 29)
        field = self.expense_inputs['expense_date']
        field.open_calendar()
        self.press('Clear date', field.calendar_menu)
        assert field.text == ''
        self.select(field, 2020, 'Jan', 12)

    def expense_calendar(self):
        self.capture('friendly-expense-date')
        self.press('Save expense')
        assert self.store.expense_total(self.trip_id) == 250000

    def expense_save(self):
        self.capture('clear-expense-cards')
        labels = [getattr(w, 'text', '') for w in self.root.walk()]
        assert 'Date: Jan 12, 2020' in labels
        assert 'Place/provider: Boston restaurant' in labels
        assert any(value.startswith('Shared by:') for value in labels)
        self.press('+ New expense')
        self.expense_category.text = 'Flights'

    def flight_start(self):
        self.expense_inputs['name'].text = 'Flights'
        self.expense_inputs['cost'].text = '1,000.00'
        departure = self.expense_inputs['departure_at']
        self.select(departure, 2020, 'Jan', 12)
        departure.time_input.text = '08:30'
        assert departure.text == '2020-01-12 08:30'
        self.select(departure, 2020, 'Jan', 13)
        assert departure.text == '2020-01-13 08:30'
        departure.open_calendar()
        departure.month_choice.text = 'Dec'
        departure.move_month(1)
        assert departure.year == 2021 and departure.month == 1
        self.press('Cancel', departure.calendar_menu)
        assert departure.text == '2020-01-13 08:30'
        self.scroller.scroll_y = .25

    def flight_calendar(self):
        self.capture('flight-date-and-time')
        self.press('Save expense')
        assert self.store.expense_total(self.trip_id) == 350000
        expense = self.store.expenses(self.trip_id)[0]
        assert expense['departure_at'] == '2020-01-13 08:30'
        self.show_expense_detail(expense['id'])

    def flight_save(self):
        assert any(getattr(w, 'text', '') == 'Jan 13, 2020 at 08:30' for w in self.root.walk())
        from kivy.core.window import Window
        Window.size = (320, 568)
        self.show_expense_form(self.store.expenses(self.trip_id)[0]['id'])
        self.expense_category.text = 'Lodging'
        self.scroller.scroll_y = 0

    def lodging_calendar(self):
        field = self.expense_inputs['check_in']
        field.open_calendar()
        field.year_choice.text = '2020'
        field.month_choice.text = 'Jan'

    def finished(self):
        self.capture('narrow-calendar-menu')
        field = self.expense_inputs['check_in']
        from kivy.core.window import Window
        assert field.calendar_menu.width <= Window.width
        assert field.calendar_menu.height > 0
        field.calendar_menu.export_as_image().save(str(OUTPUT / 'narrow-calendar-popup.png'))
        self.press('Cancel', field.calendar_menu)
        print('Calendar UI passed: trip/expense/flight/lodging dates, cancel/clear, leap day, month rollover, comma costs, labeled cards, narrow layout.')


with tempfile.TemporaryDirectory() as folder:
    app = CalendarSmoke(database_path=Path(folder) / 'trips.sqlite3')
    app.run()
    if app.failures:
        raise app.failures[0]
