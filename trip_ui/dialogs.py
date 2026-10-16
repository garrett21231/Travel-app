"""Settings, backup files, trip tools, duplication, and confirmation dialogs."""
from pathlib import Path
import sqlite3
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.checkbox import CheckBox
from planning_tools import backup_text, import_backup, duplicate_trip, trip_summary, MAX_BACKUP_BYTES
from trip_ui.theme import MUTED
from trip_ui.widgets import text, Action


class DialogsMixin:
    """Settings, backup files, trip tools, duplication, and confirmation dialogs.

    Mixed into TripPlannerApp; self is the one running app, not a separate
    screen instance. Shared state is documented in docs/CODE_GUIDE.md.
    """

    def show_settings(self):
        """House device-level backup actions away from everyday trip planning."""
        self.prepare_trip_selection('settings')
        self.page = 'settings'
        self.layout('Settings', self.show_home)
        self.body.add_widget(text('Backups', size=20, height=40, bold=True))
        self.body.add_widget(text('Save all trips to a file, or import a backup\nas new copies on this device.',
                                  size=14, color=MUTED, height=56))
        self.body.add_widget(Action('Export backup', lambda: self.show_document('Backup', backup_text(self.store), '.json')))
        self.body.add_widget(Action('Import backup', self.choose_backup))
        self.navigation(selected='settings')


    def show_trip_tools(self):
        """Keep occasional summary/export tools in the trip header's More menu."""
        trip_id = self.trip_id
        body = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
        popup = Popup(title='Trip tools', content=body, size_hint=(.9, None), height=dp(240))

        def open_document(summary):
            # Close the menu before opening the document preview/file actions.
            popup.dismiss()
            if summary:
                self.show_document('Trip summary', trip_summary(self.store, trip_id), '.txt')
            else:
                self.show_document('Trip backup', backup_text(self.store, [trip_id]), '.json')

        body.add_widget(Action('Readable summary', lambda: open_document(True)))
        body.add_widget(Action('Export this trip', lambda: open_document(False)))
        body.add_widget(Action('Close', popup.dismiss))
        self.trip_tools_popup = popup
        popup.open()


    def show_duplicate(self):
        body = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
        options = []
        for caption, initial in [('Clear trip and booking dates', True), ('Reset Confirmed costs to Estimated', True)]:
            row = BoxLayout(size_hint_y=None, height=dp(54))
            check = CheckBox(active=initial, size_hint_x=None, width=dp(44))
            row.add_widget(check)
            row.add_widget(text(caption, size=13, height=54))
            body.add_widget(row)
            options.append(check)
        message = text('The copy has independent travelers, photos, and expenses.', size=12, color=MUTED, height=40)
        body.add_widget(message)
        popup = Popup(title='Duplicate trip', content=body, size_hint=(.94, None), height=dp(310))
        row = BoxLayout(size_hint_y=None, height=dp(44))
        row.add_widget(Action('Cancel', popup.dismiss))
        def create():
            try:
                new_id = duplicate_trip(self.store, self.trip_id, options[0].active, options[1].active)
            except (ValueError, sqlite3.Error, OSError) as error:
                message.text = str(error)
                return
            popup.dismiss()
            self.show_detail(new_id)
        row.add_widget(Action('Create copy', create, primary=True))
        body.add_widget(row)
        self.active_popup = popup
        popup.open()


    def show_document(self, title, document, extension):
        """Preview/copy/save locally; sending to other apps remains a user action."""
        body = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
        preview = TextInput(text=document, readonly=True, font_size=sp(13), multiline=True)
        body.add_widget(preview)
        filename = 'trip-backup.json' if extension == '.json' else 'trip-summary.txt'
        path = TextInput(text=str(Path(self.user_data_dir) / 'exports' / filename), multiline=False,
                         size_hint_y=None, height=dp(44), font_size=sp(12))
        body.add_widget(text('Save path (editable)', size=12, height=20))
        body.add_widget(path)
        message = text('Backups include profile contacts and photos.' if extension == '.json' else 'Summary excludes profile contact details and photos.',
                       size=12, color=MUTED, height=40)
        body.add_widget(message)
        popup = Popup(title=title, content=body, size_hint=(.95, .9))
        row = BoxLayout(size_hint_y=None, height=dp(44))
        def save(overwrite=False):
            destination = Path(path.text.strip()).expanduser()
            if destination.exists() and not overwrite:
                self.confirm('Replace file?', str(destination), 'Replace', lambda: save(True))
                return
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(document, encoding='utf-8')
                message.text = 'Saved to ' + str(destination)
            except (OSError, ValueError):
                message.text = 'Could not save. Check the path and try again.'
        row.add_widget(Action('Copy', lambda: Clipboard.copy(document)))
        row.add_widget(Action('Save file', save))
        row.add_widget(Action('Close', popup.dismiss))
        body.add_widget(row)
        self.document_popup, self.document_text, self.document_path = popup, preview, path
        popup.open()


    def choose_backup(self):
        body = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
        chooser = FileChooserListView(path=str(Path(self.user_data_dir)), filters=['*.json'])
        body.add_widget(chooser)
        message = text('Import adds independent copies without replacing saved trips.', size=12, height=44)
        body.add_widget(message)
        popup = Popup(title='Import backup', content=body, size_hint=(.95, .9))
        row = BoxLayout(size_hint_y=None, height=dp(44))
        row.add_widget(Action('Cancel', popup.dismiss))
        def restore():
            try:
                if not chooser.selection:
                    raise ValueError('Choose a backup file first.')
                with open(chooser.selection[0], 'rb') as source:
                    raw = source.read(MAX_BACKUP_BYTES + 1)
                if len(raw) > MAX_BACKUP_BYTES:
                    raise ValueError('Backup exceeds 64 MB.')
                imported = import_backup(self.store, raw.decode('utf-8-sig'))
            except (ValueError, OSError, sqlite3.Error) as error:
                message.text = str(error)
                return
            popup.dismiss()
            self.show_detail(imported[0])
        row.add_widget(Action('Import copies', restore, primary=True))
        body.add_widget(row)
        self.backup_popup, self.backup_chooser = popup, chooser
        popup.open()


    def confirm(self, title, message, action, callback, cancel_caption='Cancel'):
        """Show a modal dialog; dismiss it before running the accepted action.

        callbacks take no arguments. cancel_caption='Later' supports the
        post-save review prompt, where Cancel would imply undoing a saved record.
        active_popup also allows smoke tests to exercise the dialog's buttons.
        """
        body = BoxLayout(orientation='vertical', spacing=dp(12), padding=dp(12))
        body.add_widget(text(message, size=15, height=70))
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(12))
        popup = Popup(title=title, content=body, size_hint=(.9, None), height=dp(230), auto_dismiss=False)
        row.add_widget(Action(cancel_caption, popup.dismiss))
        def accept():
            popup.dismiss()
            callback()
        row.add_widget(Action(action, accept, primary=True))
        body.add_widget(row)
        popup.open()
        self.active_popup = popup

