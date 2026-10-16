"""Exercise split controls using isolated data and real Kivy button events."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kivy.clock import Clock
from main import TripPlannerApp, Action
from trip_store import validate_trip, validate_traveler

OUTPUT = Path(__file__).parent / 'artifacts'
OUTPUT.mkdir(exist_ok=True)


class SplitSmoke(TripPlannerApp):
    def on_start(self):
        self.failures = []
        self.tid = self.store.save(validate_trip('Friends in Boston', 'Boston', '2000', '4'))
        self.ids = [self.store.save_traveler(self.tid, validate_traveler(name)) for name in ('Alex', 'Sam', 'Jo', 'Pat')]
        self.show_detail(self.tid, 'expenses')
        self.steps = iter([self.everyone_start, self.everyone_save, self.selected_start, self.selected_save,
                           self.custom_start, self.custom_save, self.traveler_summary, self.add_traveler,
                           self.review_prompt, self.removal, self.review_removed, self.narrow])
        Clock.schedule_once(self.step, .6)

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

    def everyone_start(self):
        self.press('+ New expense')
        self.expense_inputs['name'].text = 'Flights'
        self.expense_inputs['cost'].text = '200'
        self.expense_basis.text = 'Per person'
        assert '$800.00' in self.expense_preview.text
        self.scroller.scroll_y = .5

    def everyone_save(self):
        self.capture('everyone-split')
        self.press('Save expense')
        assert self.store.expense_total(self.tid) == 80000
        self.flight_id = self.store.expenses(self.tid)[0]['id']

    def selected_start(self):
        self.press('+ New expense')
        self.expense_inputs['name'].text = 'Hotel'
        self.expense_inputs['cost'].text = '600'
        self.expense_split_mode.text = 'Selected travelers'
        for tid, (_, check, _) in self.split_rows.items():
            check.active = tid in self.ids[:2]
        assert '2 people' in self.expense_preview.text
        self.scroller.scroll_y = .5

    def selected_save(self):
        self.capture('selected-split')
        self.press('Save expense')
        self.hotel_id = self.store.expenses(self.tid)[0]['id']
        assert self.store.expense_total(self.tid) == 140000
        self.show_expense_detail(self.hotel_id)
        assert any(getattr(w, 'text', '') == 'Alex: $300.00 USD' for w in self.root.walk())

    def custom_start(self):
        self.capture('selected-split-details')
        self.show_detail(self.tid, 'expenses')
        self.press('+ New expense')
        self.expense_inputs['name'].text = 'Dinner'
        self.expense_inputs['cost'].text = '100'
        self.expense_split_mode.text = 'Custom amounts'
        for tid, (_, check, amount) in self.split_rows.items():
            check.active = tid in self.ids[:2]
            amount.text = '70' if tid == self.ids[0] else '20'
        self.press('Save expense')
        assert self.page == 'expense_form' and 'add up' in self.expense_error.text
        self.split_rows[self.ids[1]][2].text = '30'
        self.scroller.scroll_y = .5

    def custom_save(self):
        self.capture('custom-split')
        self.press('Save expense')
        assert self.store.expense_total(self.tid) == 150000
        self.show_detail(self.tid, 'travelers')
        self.show_traveler_shares(self.ids[0])
        assert any(getattr(w, 'text', '') == '$570.00 USD' for w in self.root.walk())
        assert sum(isinstance(w, Action) and w.text == 'View expense' for w in self.root.walk()) == 3

    def traveler_summary(self):
        self.capture('traveler-share-breakdown')
        totals = [sum(s['amount_cents'] for s in self.store.traveler_shares(self.tid, tid)) for tid in self.ids]
        assert totals == [57000, 53000, 20000, 20000]
        self.show_detail(self.tid, 'travelers')
        self.press('+ New traveler')
        self.traveler_inputs['name'].text = 'Chris'

    def add_traveler(self):
        self.press('Save traveler')
        assert self.active_popup.title == 'Review expense splits'
        assert self.store.expense_total(self.tid) == 150000

    def review_prompt(self):
        self.capture('split-review-prompt')
        self.press('Review', self.active_popup)
        assert self.detail_tab == 'expenses'
        assert self.store.get_expense(self.tid, self.flight_id)['split_review']

    def removal(self):
        self.delete_traveler(self.ids[0])
        assert self.store.expense_total(self.tid) == 150000
        self.show_expense_detail(self.hotel_id)
        assert any('Alex (removed)' in getattr(w, 'text', '') for w in self.root.walk())

    def review_removed(self):
        self.capture('removed-traveler-split')
        self.press('Edit expense')
        assert self.expense_split_mode.text == 'Selected travelers'
        assert self.split_rows[self.ids[1]][1].active
        self.press('Save expense')
        assert self.store.expense_total(self.tid) == 150000
        assert not self.store.get_expense(self.tid, self.hotel_id)['split_review']
        shares = self.store.expense_shares(self.tid, self.hotel_id)
        assert len(shares) == 1 and shares[0]['amount_cents'] == 60000
        from kivy.core.window import Window
        Window.size = (320, 568)
        self.show_expense_form(self.hotel_id)
        self.expense_split_mode.text = 'Custom amounts'
        self.scroller.scroll_y = .5

    def narrow(self):
        self.capture('narrow-split-form')
        assert all(row.width > 0 for row, _, _ in self.split_rows.values())
        print('Split UI passed: everyone, selected, custom validation, traveler totals, roster review, removal, narrow layout.')


with tempfile.TemporaryDirectory() as folder:
    app = SplitSmoke(database_path=Path(folder) / 'trips.sqlite3')
    app.run()
    if app.failures:
        raise app.failures[0]
