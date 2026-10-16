"""Phone-size rendering and real button-event checks with isolated trip data."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kivy.clock import Clock
from kivy.core.window import Window
from main import TripPlannerApp, Action
from trip_store import TripStore

OUTPUT = Path(__file__).parent / 'artifacts'
OUTPUT.mkdir(exist_ok=True)


class SmokeApp(TripPlannerApp):
    def on_start(self):
        self.failures = []
        self.steps = iter([self.home, self.invalid, self.create, self.detail, self.expense_form,
                           self.expense_saved, self.expense_edit, self.expense_delete,
                           self.rich_expense_start, self.rich_expense_form, self.rich_expense_saved,
                           self.rich_lodging_form, self.rich_expense_cleanup,
                           self.traveler_start, self.traveler_form, self.traveler_saved,
                           self.traveler_photo_removed, self.traveler_deleted,
                           self.edit, self.saved, self.delete, self.narrow])
        Clock.schedule_once(self.step, 1)

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

    def capture(self, name):
        self.root.export_as_image().save(str(OUTPUT / f'{name}.png'))

    def press(self, caption, root=None):
        button = next(w for w in (root or self.root).walk() if isinstance(w, Action) and w.text == caption)
        button.dispatch('on_release')

    def home(self):
        self.capture('home')
        self.press('+ New trip')

    def invalid(self):
        self.press('Save trip')
        assert self.page == 'form' and self.error.text
        for key, value in dict(name='Weekend in Boston', destination='Boston, Massachusetts', cost='1200.99', people='3',
                               description='A few days away with friends.', start_date='2027-06-12', end_date='2027-06-15').items():
            self.inputs[key].text = value
        assert '$400.33' in self.preview.text
        self.scroller.scroll_y = 1

    def create(self):
        self.capture('create')
        self.press('Save trip')
        assert self.page == 'detail'
        assert TripStore(self.database_path).all()[0]['cost_cents'] == 120099
        # This regression fixture exercises the no-profile planning flow.
        for traveler in self.store.travelers(self.trip_id):
            self.store.delete_traveler(self.trip_id, traveler['id'])
        self.show_detail(self.trip_id)

    def detail(self):
        self.capture('detail')
        self.press('Expenses (0)')
        assert self.detail_tab == 'expenses'
        self.press('+ New expense')

    def expense_form(self):
        self.press('Save expense')
        assert self.page == 'expense_form' and self.expense_error.text
        for key, value in dict(name='Plane flight', cost='350.99', description='Round trip to Boston').items():
            self.expense_inputs[key].text = value
        self.expense_category.text = 'Flights'
        self.expense_inputs['airline'].text = 'Example Air'
        self.capture('expense-form')
        self.press('Save expense')
        assert self.detail_tab == 'expenses'
        assert TripStore(self.database_path).expense_total(self.trip_id) == 35099

    def expense_saved(self):
        self.capture('expenses')
        self.press('Edit expense')
        assert self.expense_category.text == 'Flights'
        assert self.expense_inputs['airline'].text == 'Example Air'
        assert self.expense_inputs['description'].text == 'Round trip to Boston'
        self.expense_inputs['cost'].text = '299.50'
        self.press('Save expense')
        assert self.store.expense_total(self.trip_id) == 29950
        self.press('Overview')
        assert any(getattr(w, 'text', '') == 'Planned: $299.50 USD' for w in self.root.walk())
        self.press('Expenses (1)')
        self.press('+ New expense')
        self.expense_inputs['name'].text = 'Hotel'
        self.cancel_expense_form()
        self.press('Cancel', self.active_popup)
        assert self.page == 'expense_form' and self.expense_inputs['name'].text == 'Hotel'
        self.cancel_expense_form()
        self.press('Discard', self.active_popup)
        assert len(self.store.expenses(self.trip_id)) == 1

    def expense_edit(self):
        self.press('Delete')
        self.press('Cancel', self.active_popup)
        assert len(self.store.expenses(self.trip_id)) == 1
        self.press('Delete')
        self.press('Delete', self.active_popup)
        assert self.store.expense_total(self.trip_id) == 0

    def expense_delete(self):
        self.press('Overview')
        self.press('Edit trip')
        assert self.inputs['destination'].text == 'Boston, Massachusetts'
        self.inputs['people'].text = '4'
        self.inputs['cost'].text = '800.00'
        self.press('Save trip')
        assert self.store.get(self.trip_id)['people'] == 4

    def rich_expense_start(self):
        self.press('Expenses (0)')
        self.press('+ New expense')
        self.expense_category.text = 'Flights'
        self.expense_basis.text = 'Per person'
        for key, value in dict(name='Boston flight', cost='100.25', expense_date='2027-06-12', provider='Direct booking',
                               airline='Example Air', flight_number='EX123', departure_airport='LAX', arrival_airport='BOS',
                               departure_at='2027-06-12 08:30', arrival_at='2027-06-12 17:00', description='Carry-on included').items():
            self.expense_inputs[key].text = value
        assert '$401.00' in self.expense_preview.text
        assert self.expense_inputs['departure_at'].parent is self.expense_specific
        assert self.expense_inputs['check_in'].parent is None

    def rich_expense_form(self):
        self.capture('flight-expense-form')
        self.scroller.scroll_y = 0
        self.press('Save expense')
        assert self.store.expense_total(self.trip_id) == 40100
        self.press('View details')
        assert self.page == 'expense_detail'
        assert any(getattr(w, 'text', '') == 'EX123' for w in self.root.walk())

    def rich_expense_saved(self):
        self.capture('flight-expense-details')
        self.show_detail(self.trip_id, 'expenses')
        self.press('+ New expense')
        self.expense_category.text = 'Lodging'
        assert self.expense_inputs['check_in'].parent is self.expense_specific
        assert self.expense_inputs['departure_at'].parent is None
        for key, value in dict(name='Boston hotel', cost='200', provider='Boston Hotel', check_in='2027-06-15', check_out='2027-06-12').items():
            self.expense_inputs[key].text = value
        self.press('Save expense')
        assert self.page == 'expense_form' and 'Check-out' in self.expense_error.text
        self.expense_inputs['check_in'].text = '2027-06-12'
        self.expense_inputs['check_out'].text = '2027-06-15'
        self.scroller.scroll_y = 1

    def rich_lodging_form(self):
        self.capture('lodging-expense-form')
        self.press('Save expense')
        assert self.store.expense_total(self.trip_id) == 60100

    def rich_expense_cleanup(self):
        self.capture('categorized-expenses')
        for expense in self.store.expenses(self.trip_id):
            self.store.delete_expense(self.trip_id, expense['id'])
        self.show_detail(self.trip_id)

    def edit(self):
        self.show_saved()
        self.show_detail(self.trip_id)

    def traveler_start(self):
        self.press('Travelers (0)')
        self.press('+ New traveler')
        self.press('Save traveler')
        assert self.page == 'traveler_form' and self.traveler_error.text
        for key, value in dict(name='Alex Morgan', age='28', phone='+1 (555) 123-4567',
                               email='alex@example.com', gender='Nonbinary').items():
            self.traveler_inputs[key].text = value
        self.press('Choose photo')
        self.press('Cancel', self.photo_picker)
        assert self.traveler_photo is None
        assert not self.select_traveler_photo(Path(__file__).parent / 'missing.png')
        self.press('Choose photo')
        asset = Path(__file__).resolve().parents[1] / 'assets' / 'field.png'
        self.photo_chooser.path = str(asset.parent)
        self.photo_chooser.selection = [str(asset)]
        self.press('Use photo', self.photo_picker)
        assert self.photo_preview.texture is not None
        self.scroller.scroll_y = 1

    def traveler_form(self):
        self.capture('traveler-form')
        self.press('Save traveler')
        saved = TripStore(self.database_path).travelers(self.trip_id)[0]
        assert saved['name'] == 'Alex Morgan' and saved['image_bytes']

    def traveler_saved(self):
        self.capture('travelers')
        self.press('Edit traveler')
        assert self.traveler_inputs['email'].text == 'alex@example.com'
        assert self.photo_preview.texture is not None
        self.traveler_inputs['age'].text = '29'
        self.press('Remove photo')
        self.cancel_traveler_form()
        self.press('Cancel', self.active_popup)
        assert self.page == 'traveler_form'
        self.press('Save traveler')
        saved = self.store.travelers(self.trip_id)[0]
        assert saved['age'] == 29 and saved['image_bytes'] is None

    def traveler_photo_removed(self):
        self.capture('travelers-no-photo')
        self.press('Delete')
        self.press('Cancel', self.active_popup)
        assert len(self.store.travelers(self.trip_id)) == 1
        self.press('Delete')
        self.press('Delete', self.active_popup)
        assert self.store.travelers(self.trip_id) == []

    def traveler_deleted(self):
        self.press('+ New traveler')
        self.traveler_inputs['name'].text = 'Unsaved traveler'
        self.cancel_traveler_form()
        self.press('Discard', self.active_popup)
        assert self.detail_tab == 'travelers' and self.store.travelers(self.trip_id) == []

    def saved(self):
        self.capture('saved')
        self.show_detail(self.store.all()[0]['id'])
        self.press('Delete trip')
        self.press('Cancel', self.active_popup)
        assert len(self.store.all()) == 1
        self.press('Delete trip')
        self.press('Delete', self.active_popup)

    def delete(self):
        assert self.page == 'saved' and self.store.all() == []
        Window.size = (320, 568)
        self.show_form()

    def narrow(self):
        self.capture('narrow')
        assert all(field.width > 0 for field in self.inputs.values())
        print('UI smoke passed: trips, expenses, travelers, photo selection/removal, validation, persistence, edit/delete/cancel, phone rendering.')


with tempfile.TemporaryDirectory() as folder:
    app = SmokeApp(database_path=Path(folder) / 'trips.sqlite3')
    app.run()
    if app.failures:
        raise app.failures[0]
