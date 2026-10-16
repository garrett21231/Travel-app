"""Exercise Settings navigation and chronological year groups with temporary data."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kivy.clock import Clock
from kivy.core.window import Window
from main import Action, TripPlannerApp
from trip_store import validate_trip


class NavigationSmoke(TripPlannerApp):
    def on_start(self):
        self.failure = None
        Clock.schedule_once(self.check, .5)

    def press(self, caption):
        next(w for w in self.root.walk() if isinstance(w, Action) and w.text == caption).dispatch('on_release')

    def check_selection(self, selected):
        tabs = [w for w in self.root.walk() if isinstance(w, Action) and w.text in ('Upcoming', 'All trips', 'Settings')]
        assert len(tabs) == 3
        assert [w.text for w in tabs if hasattr(w, 'fill')] == [selected]

    def check(self, _):
        try:
            self.check_selection('Upcoming')
            self.press('All trips')
            self.check_selection('All trips')
            assert any(getattr(w, 'text', '').startswith('Your saved trips will appear') for w in self.root.walk())
            # Deliberately insert out of date order, including a cross-year trip.
            for name, start, end in [('Older', '2024-07-01', '2024-07-03'),
                                     ('Undated', '', ''),
                                     ('December', '2027-12-30', '2028-01-02'),
                                     ('January', '2027-01-12', '2027-01-15')]:
                self.store.save(validate_trip(name, start_date=start, end_date=end))
            self.show_home()
            actions = [w.text for w in self.root.walk() if isinstance(w, Action)]
            assert 'Past trips' not in actions and 'Import backup' not in actions and 'Export backup' not in actions
            self.press('All trips (4)')
            # Kivy stores children in reverse visual order. Flatten each card's
            # labels to verify headings and cards together, not merely sort keys.
            content = []
            expected = ['2027', 'December', 'January', '2024', 'Older', 'Dates undecided', 'Undated']
            for widget in reversed(self.body.children):
                content.extend(w.text for w in widget.walk(restrict=True) if getattr(w, 'text', '') in expected)
            assert content == expected, content
            self.press('+ New trip')
            self.cancel_form()
            assert self.page == 'saved'
            Window.size = (320, 568)
            self.press('Settings')
            self.check_selection('Settings')
            self.press('Export backup')
            assert 'December' in self.document_text.text
            self.document_popup.dismiss()
            self.press('Import backup')
            self.backup_popup.dismiss()
            Clock.schedule_once(self.capture, .6)
        except Exception as error:
            self.failure = error
            self.stop()

    def capture(self, _):
        try:
            output = Path(__file__).parent / 'artifacts'
            output.mkdir(exist_ok=True)
            self.root.export_as_image().save(str(output / 'settings-narrow.png'))
            self.press('All trips')
            Clock.schedule_once(self.finish, .6)
        except Exception as error:
            self.failure = error
            self.stop()

    def finish(self, _):
        self.root.export_as_image().save(str(Path(__file__).parent / 'artifacts' / 'all-trips-years.png'))
        print('Navigation UI passed: empty list, year/date order, undated/cross-year trips, form return, Settings backups, narrow tabs.')
        self.stop()


with tempfile.TemporaryDirectory() as folder:
    app = NavigationSmoke(database_path=Path(folder) / 'trips.sqlite3')
    app.run()
    if app.failure:
        raise app.failure
