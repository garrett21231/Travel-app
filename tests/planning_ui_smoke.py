"""Integration check for the planning additions; all data/files are temporary."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kivy.clock import Clock
from main import TripPlannerApp, Action
from trip_store import validate_traveler

OUTPUT = Path(__file__).parent / 'artifacts'
OUTPUT.mkdir(exist_ok=True)


class PlanningSmoke(TripPlannerApp):
    def on_start(self):
        self.failures = []
        self.steps = iter([self.start, self.minimum, self.notes, self.budget, self.personal, self.shared,
                           self.overview, self.copy_trip, self.undo_expense, self.backup,
                           self.export_file, self.import_file, self.connections, self.save_connections,
                           self.undo_trip, self.restore_trip, self.expiration, self.finished])
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
        Clock.schedule_once(self.step, .6)

    def press(self, caption, root=None):
        next(w for w in (root or self.root).walk() if isinstance(w, Action) and w.text == caption).dispatch('on_release')

    def capture(self, name):
        self.root.export_as_image().save(str(OUTPUT / f'{name}.png'))

    def start(self):
        self.press('+ New trip')
        self.inputs['name'].text = 'Snowboarding weekend'

    def minimum(self):
        self.capture('name-only-trip')
        self.press('Save trip')
        self.original_trip = self.trip_id
        assert self.store.get(self.trip_id)['budget_set'] == 0
        self.you = self.store.travelers(self.trip_id)[0]['id']
        self.press('Edit notes')
        self.notes_input.text = 'Compare rental prices. Friend already owns a ski pass.'
        self.press('Save notes')

    def notes(self):
        self.press('Edit trip')
        self.inputs['destination'].text = 'Mountain resort\nBoston'
        self.inputs['cost'].text = '1,000.00'
        self.inputs['people'].text = '2'
        self.inputs['start_date'].text = '2027-01-12'
        self.inputs['end_date'].text = '2027-01-15'
        self.press('Save trip')
        self.friend = self.store.save_traveler(self.trip_id, validate_traveler('Friend'))

    def budget(self):
        self.show_detail(self.trip_id, 'expenses')
        self.press('+ New expense')
        self.expense_inputs['name'].text = 'Your ski pass'
        self.expense_inputs['cost'].text = '250'
        self.expense_category.text = 'Activities'
        self.expense_split_mode.text = 'Selected travelers'
        for tid, (_, check, _) in self.split_rows.items():
            check.active = tid == self.you
        self.press('Save expense')

    def personal(self):
        self.press('+ New expense')
        self.expense_inputs['name'].text = 'Accommodation'
        self.expense_inputs['cost'].text = '600'
        self.expense_category.text = 'Lodging'
        self.expense_status.text = 'Confirmed'
        self.press('Save expense')

    def shared(self):
        self.show_detail(self.trip_id)
        assert self.store.expense_total(self.trip_id) == 85000
        labels = [getattr(w, 'text', '') for w in self.root.walk()]
        assert 'Remaining: $150.00 USD' in labels
        assert 'You: $550.00 USD' in labels
        assert 'Friend: $300.00 USD' in labels

    def overview(self):
        self.capture('planning-overview')
        self.press('Duplicate trip')
        self.press('Create copy', self.active_popup)
        assert self.trip_id != self.original_trip
        assert self.store.get(self.trip_id)['start_date'] == ''
        assert all(e['cost_status'] == 'estimated' for e in self.store.expenses(self.trip_id))

    def copy_trip(self):
        self.capture('duplicated-trip')
        self.show_detail(self.trip_id, 'expenses')
        self.press('Delete')
        self.press('Delete', self.active_popup)
        assert len(self.store.expenses(self.trip_id)) == 1
        assert self.undo_event.timeout == 10

    def undo_expense(self):
        self.capture('undo-expense')
        self.press('Undo')
        assert len(self.store.expenses(self.trip_id)) == 2
        assert self.store.expense_total(self.trip_id) == 85000
        self.show_detail(self.trip_id)
        assert not any(getattr(w, 'text', '') in ('Readable summary', 'Export this trip') for w in self.root.walk())
        self.press('More')
        self.press('Readable summary', self.trip_tools_popup)
        assert 'You: $550.00' in self.document_text.text
        self.press('Close', self.document_popup)
        self.press('More')
        self.press('Export this trip', self.trip_tools_popup)
        self.document_path.text = str(Path(self.database_path).parent / 'backup.json')

    def backup(self):
        self.press('Save file', self.document_popup)
        assert Path(self.document_path.text).is_file()

    def export_file(self):
        self.press('Close', self.document_popup)
        self.show_home()
        self.press('Settings')
        self.press('Import backup')
        self.backup_chooser.path = str(Path(self.database_path).parent)
        self.backup_chooser.selection = [str(Path(self.database_path).parent / 'backup.json')]

    def import_file(self):
        self.press('Import copies', self.backup_popup)
        assert len(self.store.all()) == 3
        assert self.store.expense_total(self.trip_id) == 85000
        self.show_detail(self.trip_id, 'expenses')
        self.press('+ New expense')
        self.expense_category.text = 'Flights'
        self.expense_inputs['name'].text = 'One ticket, two flights'
        self.expense_inputs['cost'].text = '450'
        self.expense_inputs['departure_airport'].text = 'Boston'
        self.expense_inputs['arrival_airport'].text = 'London'
        self.press('+ Add connecting flight')
        self.segment_rows[0]['departure_airport'].text = 'London'
        self.segment_rows[0]['arrival_airport'].text = 'Rome'
        self.segment_rows[0]['flight_number'].text = 'EX123'
        self.scroller.scroll_y = .2

    def connections(self):
        self.capture('connecting-flight-form')
        self.press('Save expense')
        assert self.store.expense_total(self.trip_id) == 130000
        expense = self.store.expenses(self.trip_id)[0]
        self.show_expense_detail(expense['id'])
        assert any(getattr(w, 'text', '') == 'Flight 2 (same booking)' for w in self.root.walk())

    def save_connections(self):
        self.capture('connecting-flight-details')
        self.show_detail(self.trip_id)
        self.deleted_trip = self.trip_id
        self.press('Delete trip')
        self.press('Delete', self.active_popup)
        assert self.store.get(self.deleted_trip) is None

    def undo_trip(self):
        self.capture('undo-trip')
        self.press('Undo')
        assert self.trip_id == self.deleted_trip
        assert self.store.expense_total(self.trip_id) == 130000

    def restore_trip(self):
        self.show_detail(self.trip_id, 'travelers')
        self.profile = self.store.travelers(self.trip_id)[0]['id']
        self.delete_traveler(self.profile)
        assert self.store.get_traveler(self.trip_id, self.profile) is None
        self.press('Undo')
        assert self.store.get_traveler(self.trip_id, self.profile)
        self.delete_traveler(self.profile)
        self.expire_undo()

    def expiration(self):
        assert self.undo_token is None
        assert self.store.get_traveler(self.trip_id, self.profile) is None
        assert self.store.expense_total(self.original_trip) == 85000
        from kivy.core.window import Window
        Window.size = (320, 568)
        self.show_detail(self.original_trip)

    def finished(self):
        self.capture('narrow-planning-overview')
        print('Planning UI passed: name-only/default You, notes, budgets, statuses, duplication, export/import, connections, Undo/expiry, narrow layout.')


with tempfile.TemporaryDirectory() as folder:
    app = PlanningSmoke(database_path=Path(folder) / 'trips.sqlite3')
    app.run()
    if app.failures:
        raise app.failures[0]
