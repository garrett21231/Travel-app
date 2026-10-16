"""Launch Trip Planner with python main.py (or python main.py --demo).

TripPlannerApp is the only application class. It owns startup and shared state;
trip_ui/ organizes screens and helpers without changing their behavior.
See docs/CODE_GUIDE.md for the module map and editing examples.
"""
from pathlib import Path
import tempfile
import sys
from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.utils import platform
from trip_store import TripStore, validate_trip, validate_expense, validate_traveler
from trip_ui.theme import BLACK
from trip_ui.widgets import Action  # Public compatibility for UI scripts.
from trip_ui.navigation import NavigationMixin
from trip_ui.trips import TripScreensMixin
from trip_ui.expenses import ExpenseScreensMixin
from trip_ui.travelers import TravelerScreensMixin
from trip_ui.dialogs import DialogsMixin
from trip_ui.deletion import DeletionMixin


class TripPlannerApp(
    NavigationMixin,
    TripScreensMixin,
    ExpenseScreensMixin,
    TravelerScreensMixin,
    DialogsMixin,
    DeletionMixin,
    App,
):
    """The only Kivy App: own shared state and assemble the UI feature classes.

    Feature methods are organized under trip_ui/ and remain callable on this
    instance (for example, self.show_detail()). Start with docs/CODE_GUIDE.md
    to find a feature. Run this file to launch; do not run the mixins directly.
    """
    title = 'Trip Planner'

    def __init__(self, database_path=None, **kwargs):
        """Accept an optional database override so UI tests use isolated data."""
        super().__init__(**kwargs)
        self.database_path = database_path
        self.page = 'home'
        self.trip_id = None
        self.undo_token = None
        self.undo_event = None
        self.undo_bar = None
        self.selection_page = None
        self.selected_trip_ids = set()

    def build(self):
        """Kivy startup hook: create storage/root, bind Back, and render home."""
        Window.clearcolor = BLACK
        Window.softinput_mode = 'below_target'
        if platform not in ('android', 'ios'):
            Window.size = (375, 812)
            Window.minimum_width, Window.minimum_height = 320, 480
        self.store = TripStore(self.database_path or Path(self.user_data_dir) / 'trips.sqlite3')
        self.shell = BoxLayout(orientation='vertical')
        Window.bind(on_keyboard=self.keyboard)
        self.show_home()
        return self.shell

if __name__ == '__main__':
    # Demo data lives in a disposable database and never touches saved plans.
    if '--demo' in sys.argv:
        sys.argv.remove('--demo')
        with tempfile.TemporaryDirectory() as folder:
            app = TripPlannerApp(database_path=Path(folder) / 'demo.sqlite3')
            store = TripStore(app.database_path)
            tid = store.save(validate_trip('Snowboarding weekend', 'Mountain resort', '1000', '2'))
            you = store.save_traveler(tid, validate_traveler('You'))
            friend = store.save_traveler(tid, validate_traveler('Friend'))
            store.save_expense(tid, validate_expense('Accommodation', '600', category='Lodging', cost_status='confirmed'))
            store.save_expense(tid, validate_expense('Your ski pass', '250', category='Activities', split_mode='selected'), participant_ids=[you])
            app.run()
    else:
        TripPlannerApp().run()

