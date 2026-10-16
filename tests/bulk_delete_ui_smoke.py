"""Select/delete trips through the UI, using only a temporary database."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kivy.clock import Clock
from kivy.core.window import Window
from main import Action, TripPlannerApp
from trip_store import validate_trip, validate_expense


class BulkDeleteSmoke(TripPlannerApp):
    def on_start(self):
        self.failure = None
        self.ids = [self.store.save(validate_trip(name), create_default_traveler=True)
                    for name in ('Test weekend', 'Another test trip', 'Keep this trip')]
        self.past = self.store.save(validate_trip('Past trip', start_date='2020-01-01', end_date='2020-01-03'))
        self.expense = self.store.save_expense(self.ids[0], validate_expense('Dinner', '30'))
        Window.size = (320, 568)
        self.show_home()
        self.steps = iter([self.select, self.selected, self.cancel_confirmation, self.undo,
                           self.restored, self.select_all, self.past_selection, self.expired, self.finished])
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

    def press(self, caption, root=None):
        next(w for w in (root or self.root).walk() if isinstance(w, Action) and w.text == caption).dispatch('on_release')

    def capture(self, name):
        output = Path(__file__).parent / 'artifacts'
        output.mkdir(exist_ok=True)
        self.root.export_as_image().save(str(output / (name + '.png')))

    def select(self):
        self.press('Select')
        assert self.delete_selected_action.disabled
        assert self.past not in self.selectable_trip_ids
        # Checkboxes and whole-card taps share the same selection state.
        self.trip_selection_checks[self.ids[0]].active = True
        check = self.trip_selection_checks[self.ids[1]]
        next(w for w in check.parent.children if w is not check).dispatch('on_release')
        assert self.selected_trip_ids == set(self.ids[:2])
        assert self.page == 'home'

    def selected(self):
        self.capture('bulk-delete-selection')
        self.press('Delete (2)')
        assert len(self.store.all()) == 4
        self.press('Cancel', self.active_popup)
        assert len(self.selected_trip_ids) == 2

    def cancel_confirmation(self):
        self.press('Delete (2)')
        self.press('Delete', self.active_popup)
        assert self.page == 'home' and self.selection_page is None
        assert {t['id'] for t in self.store.all()} == {self.ids[2], self.past}
        assert self.undo_event.timeout == 10

    def undo(self):
        self.capture('bulk-delete-undo')
        self.press('Undo')
        assert self.page == 'home'
        assert len(self.store.all()) == 4
        assert self.store.expense_total(self.ids[0]) == 3000
        assert len(self.store.expense_shares(self.ids[0], self.expense)) == 1

    def restored(self):
        self.press('Select')
        self.press('Select all')
        assert self.selected_trip_ids == set(self.ids)
        self.press('Deselect all')
        assert not self.selected_trip_ids and self.delete_selected_action.disabled
        self.trip_selection_checks[self.ids[0]].active = True
        self.keyboard(None, 27)
        assert self.selection_page is None and not self.selected_trip_ids
        self.press('Select')
        self.trip_selection_checks[self.ids[0]].active = True
        self.press('All trips')
        assert self.selection_page is None and not self.selected_trip_ids

    def select_all(self):
        self.press('Select')
        self.press('Select all')
        assert self.selected_trip_ids == set(self.ids + [self.past])
        self.press('Cancel')
        assert self.selection_page is None
        self.press('Select')
        self.trip_selection_checks[self.past].active = True

    def past_selection(self):
        self.capture('bulk-delete-past-trip')
        self.press('Delete (1)')
        self.press('Delete', self.active_popup)
        assert self.page == 'saved'
        self.expire_undo()
        assert self.store.get(self.past) is None and len(self.store.all()) == 3
        self.press('Select')
        self.press('Select all')
        self.press('Delete (3)')
        self.press('Delete', self.active_popup)

    def expired(self):
        assert self.store.all() == []
        self.capture('bulk-delete-empty-list')
        self.press('Undo')
        assert self.page == 'saved' and len(self.store.all()) == 3
        assert self.selection_page is None

    def finished(self):
        print('Bulk delete UI passed: cards/checkboxes, selected count, cancel, visible-only Select all, Back, tab switching, batch Undo, expiration, empty list, narrow screen.')


with tempfile.TemporaryDirectory() as folder:
    app = BulkDeleteSmoke(database_path=Path(folder) / 'trips.sqlite3')
    app.run()
    if app.failure:
        raise app.failure
