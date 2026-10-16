"""The shared ten-second Undo lifecycle for single records and trip groups."""
import sqlite3
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from planning_tools import stage_delete, finish_delete
from trip_ui.theme import BLACK
from trip_ui.widgets import wrapped_text, Panel, Action


class DeletionMixin:
    """The shared ten-second Undo lifecycle for single records and trip groups.

    Mixed into TripPlannerApp; self is the one running app, not a separate
    screen instance. Shared state is documented in docs/CODE_GUIDE.md.
    """

    def attach_undo(self):
        """Reattach the most recent Undo action after navigation rebuilds the page."""
        if not self.undo_token:
            return
        if self.undo_bar and self.undo_bar.parent:
            self.undo_bar.parent.remove_widget(self.undo_bar)
        self.undo_bar = Panel(82)
        row = BoxLayout()
        caption = (f"{len(self.undo_token['ids'])} trips deleted / Undo for 10 seconds" if self.undo_token['kind'] == 'trip_batch'
                   else 'Deleted / Undo available for 10 seconds')
        row.add_widget(wrapped_text(caption, size=12, color=BLACK, height=44))
        row.add_widget(Action('Undo', self.undo_delete, size_hint_x=None, width=dp(68)))
        self.undo_bar.add_widget(row)
        self.shell.add_widget(self.undo_bar)


    def begin_delete(self, kind, record_id):
        """Only the most recent deletion remains recoverable in this open session."""
        self.expire_undo()
        self.undo_token = stage_delete(self.store, kind, record_id)
        self.undo_event = Clock.schedule_once(self.expire_undo, 10)


    def expire_undo(self, *_):
        if self.undo_event:
            self.undo_event.cancel()
            self.undo_event = None
        if self.undo_token:
            try:
                finish_delete(self.store, self.undo_token)
            except (sqlite3.Error, OSError):
                self.confirm('Deletion not finished', 'The item is still hidden. Restart the app to finish removal.', 'OK', lambda: None)
            self.undo_token = None
        if self.undo_bar and self.undo_bar.parent:
            self.undo_bar.parent.remove_widget(self.undo_bar)
        self.undo_bar = None


    def undo_delete(self):
        token = self.undo_token
        if not token:
            return
        try:
            finish_delete(self.store, token, undo=True)
        except (sqlite3.Error, OSError):
            self.confirm('Undo failed', 'Please try again while Undo is available.', 'OK', lambda: None)
            return
        self.undo_token = None
        self.expire_undo()
        if token['kind'] == 'trip_batch':
            (self.show_saved if token['return_page'] == 'saved' else self.show_home)()
            return
        tab = 'expenses' if token['kind'] == 'expenses' else 'travelers' if token['kind'] == 'travelers' else 'overview'
        self.show_detail(token['trip_id'], tab)


    def on_stop(self):
        self.expire_undo()

