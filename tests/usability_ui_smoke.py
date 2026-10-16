"""Check budget states, expense filters, fixed tabs, and wrapping at phone size."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kivy.clock import Clock
from kivy.core.window import Window
from main import Action, TripPlannerApp
from trip_store import validate_trip, validate_expense, validate_traveler


class UsabilitySmoke(TripPlannerApp):
    def on_start(self):
        self.failure = None
        Window.size = (320, 568)
        self.tid = self.store.save(validate_trip('A longer summer trip with family and friends',
                                               'Boston\nA destination with a longer name', '1000', '4'))
        self.store.save_expense(self.tid, validate_expense('Shared flight', '400', category='Flights'))
        self.store.save_traveler(self.tid, validate_traveler('You'))
        self.store.save_traveler(self.tid, validate_traveler('Friend with a longer name', email='a.longer.email.address@example.com'))
        self.store.save_expense(self.tid, validate_expense('Dinner', '150', category='Food & drink'))
        self.store.save_expense(self.tid, validate_expense('Hotel', '300', category='Lodging'))
        self.steps = iter([self.overview, self.pinned, self.category, self.combined, self.review,
                           self.travelers, self.budget_states, self.finished,
                           self.fresh_trip, self.fresh_roster])
        self.show_detail(self.tid)
        Clock.schedule_once(self.step, .6)

    def step(self, _):
        try:
            next(self.steps)()
        except StopIteration:
            self.stop()
            return
        except Exception as error:
            self.failure = error
            self.stop()
            return
        Clock.schedule_once(self.step, .6)

    def labels(self):
        return [getattr(w, 'text', '') for w in self.root.walk()]

    def press(self, caption, root=None):
        next(w for w in (root or self.root).walk() if isinstance(w, Action) and w.text == caption).dispatch('on_release')

    def check_selection(self, selected, heading):
        tabs = [w for w in self.trip_tabs.children if isinstance(w, Action)]
        assert [w.text for w in tabs if hasattr(w, 'fill')] == [selected]
        assert heading in [getattr(w, 'text', '') for w in self.body.children]

    def capture(self, name):
        output = Path(__file__).parent / 'artifacts'
        output.mkdir(exist_ok=True)
        self.root.export_as_image().save(str(output / (name + '.png')))

    def overview(self):
        self.check_selection('Overview', 'Trip overview')
        assert 'Remaining: $150.00 USD' in self.labels()
        assert '2 of 4 travelers added' in self.labels()
        self.capture('compact-overview-long-text')
        self.tab_y = self.trip_tabs.y
        self.scroller.scroll_y = 0

    def pinned(self):
        assert abs(self.trip_tabs.y - self.tab_y) < 1
        assert self.trip_tabs.parent is not self.body
        self.press('Delete trip')
        assert any('Undo is available for 10 seconds.' in getattr(w, 'text', '') for w in self.active_popup.walk())
        self.press('Cancel', self.active_popup)
        self.press('+ Add traveler')
        assert self.page == 'traveler_form'
        self.cancel_traveler_form()
        self.show_detail(self.tid, 'expenses')
        self.expense_filter_category.text = 'Lodging'

    def category(self):
        self.check_selection('Expenses (3)', 'Expenses')
        assert 'Showing 1 of 3 expenses' in self.labels()
        assert 'Hotel' in self.labels() and 'Dinner' not in self.labels()
        assert '$850.00 USD' in self.labels()
        self.expense_filter_review.active = True
        self.scroller.scroll_y = 0

    def combined(self):
        assert 'Showing 0 of 3 expenses' in self.labels()
        assert any('No expenses match' in value for value in self.labels())
        self.capture('expense-filters-empty')
        self.expense_filter_category.text = 'All categories'
        self.scroller.scroll_y = 0

    def review(self):
        assert 'Showing 1 of 3 expenses' in self.labels()
        assert 'Shared flight' in self.labels() and 'Hotel' not in self.labels()
        assert '$850.00 USD' in self.labels()
        self.capture('expense-filters-review')
        self.press('Clear filters')
        assert 'Showing 3 of 3 expenses' in self.labels()
        self.show_detail(self.tid, 'travelers')
        self.scroller.scroll_y = .65

    def travelers(self):
        self.check_selection('Travelers (2)', 'Travelers')
        email = next(w for w in self.root.walk() if getattr(w, 'text', '').startswith('Email: a.longer'))
        assert not email.shorten and email.height >= email.texture_size[1]
        self.capture('wrapped-traveler-details')
        with self.store.connect() as db:
            db.execute('UPDATE trips SET cost_cents=80000 WHERE id=?', (self.tid,))
        self.show_detail(self.tid)
        assert 'Over budget: $50.00 USD' in self.labels()
        with self.store.connect() as db:
            db.execute('UPDATE trips SET budget_set=0 WHERE id=?', (self.tid,))
        self.show_detail(self.tid)

    def budget_states(self):
        assert 'Budget: Not set' in self.labels()
        assert not any(value.startswith('Remaining:') for value in self.labels())
        self.capture('unset-budget-overview')
        self.show_detail(self.tid, 'expenses')
        self.scroller.scroll_y = .35

    def finished(self):
        self.capture('expense-filters-phone')
        print('Usability UI passed: budgets, roster shortcut, fixed tabs, wrapping, category/review filters, unchanged totals, Undo wording.')

    def fresh_trip(self):
        self.show_form()
        self.inputs['name'].text = 'A new group trip'
        self.inputs['people'].text = '4'
        self.save_form()
        assert 'You: $0.00 USD' in self.labels()
        assert [t['name'] for t in self.store.travelers(self.trip_id)] == ['You']
        self.scroller.scroll_y = .5

    def fresh_roster(self):
        self.capture('fresh-trip-traveler-costs')
        assert 'You: $0.00 USD' in self.labels()
        visual_order = [getattr(w, 'text', '') for w in reversed(self.body.children)]
        assert visual_order.index('Cost by traveler') < visual_order.index('You: $0.00 USD') < visual_order.index('+ Add traveler')
        self.press('+ Add traveler')
        self.traveler_inputs['name'].text = 'Friend'
        self.press('Save traveler')
        self.show_detail(self.trip_id)
        assert 'You: $0.00 USD' in self.labels() and 'Friend: $0.00 USD' in self.labels()
        assert len(self.store.travelers(self.trip_id)) == 2
        # Creating another, solo trip still starts with one default profile.
        self.show_form()
        self.inputs['name'].text = 'Solo trip'
        self.save_form()
        assert 'You: $0.00 USD' in self.labels() and '+ Add traveler' not in self.labels()
        print('Fresh-trip check passed: You appears before Add traveler, remains after roster additions, and appears for solo trips.')


with tempfile.TemporaryDirectory() as folder:
    app = UsabilitySmoke(database_path=Path(folder) / 'trips.sqlite3')
    app.run()
    if app.failure:
        raise app.failure
