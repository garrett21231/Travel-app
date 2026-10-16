"""Traveler cards, personal costs, profile forms, and local photo selection."""
from pathlib import Path
from io import BytesIO
import sqlite3
from kivy.core.image import Image as CoreImage
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from trip_store import validate_traveler, photo_format, MAX_PHOTO_BYTES, money
from trip_ui.theme import BLACK, BLUE, MUTED, RED
from trip_ui.widgets import text, wrapped_text, content_panel, Panel, Action


class TravelerScreensMixin:
    """Traveler cards, personal costs, profile forms, and local photo selection.

    Mixed into TripPlannerApp; self is the one running app, not a separate
    screen instance. Shared state is documented in docs/CODE_GUIDE.md.
    """

    def photo_texture(self, data):
        """Decode stored PNG/JPEG bytes into a Kivy texture for display."""
        # Load the saved bytes, not a path to the user's original photo.
        return CoreImage(BytesIO(data), ext=photo_format(data)).texture


    def traveler_progress(self, trip, travelers, shortcut=True):
        """Distinguish the planned group size from the named profiles added."""
        count, planned = len(travelers), trip['people']
        caption = f'{count} of {planned} travelers added' if count <= planned else f'{count} travelers added / {planned} people planned'
        self.body.add_widget(wrapped_text(caption, color=MUTED))
        if count < planned:
            self.body.add_widget(wrapped_text('Add the remaining travelers to assign expenses by name. Existing splits stay unchanged until reviewed.', size=12, color=MUTED))
            if shortcut:
                self.body.add_widget(Action('+ Add traveler', self.show_traveler_form))
        elif count > planned:
            self.body.add_widget(wrapped_text('More travelers are added than planned. Update the headcount in Edit trip if needed.', size=12, color=RED))


    def show_travelers(self, trip, travelers):
        """Append profile/photo cards, each traveler's total share, and review links."""
        self.traveler_progress(trip, travelers, shortcut=False)
        if any(expense['split_review'] for expense in self.store.expenses(self.trip_id)):
            self.body.add_widget(Action('Review expense splits', lambda: self.show_detail(self.trip_id, 'expenses')))
        self.body.add_widget(Action('+ New traveler', self.show_traveler_form, primary=True))
        if not travelers:
            panel = Panel(104)
            panel.add_widget(text('No travelers added yet.\nAdd the people going on your trip above.', color=BLACK, height=76, bold=True))
            self.body.add_widget(panel)
        for traveler in travelers:
            panel = content_panel()
            if traveler['image_bytes']:
                try:
                    panel.add_widget(Image(texture=self.photo_texture(traveler['image_bytes']), size_hint_y=None, height=dp(96)))
                except Exception:
                    panel.add_widget(text('Photo unavailable', color=BLACK, height=96))
            panel.add_widget(wrapped_text(traveler['name'], size=16, color=BLACK, bold=True))
            age = str(traveler['age']) if traveler['age'] is not None else 'Not set'
            for caption, value in [('Age', age), ('Phone', traveler['phone']), ('Email', traveler['email']), ('Gender', traveler['gender'])]:
                panel.add_widget(wrapped_text(f"{caption}: {value or 'Not set'}", color=BLACK, size=13, height=20))
            total = sum(share['amount_cents'] for share in self.store.traveler_shares(self.trip_id, traveler['id']))
            panel.add_widget(text(f'Total share: {money(total)} USD', color=BLACK, bold=True, height=24))
            panel.add_widget(Action('View shares', lambda tid=traveler['id']: self.show_traveler_shares(tid)))
            row = BoxLayout(size_hint_y=None, height=dp(44))
            traveler_id = traveler['id']
            row.add_widget(Action('Edit traveler', lambda tid=traveler_id: self.show_traveler_form(tid)))
            row.add_widget(Action('Delete', lambda tid=traveler_id: self.confirm('Delete traveler?',
                                  'Saved shares stay; splits need review.\nUndo is available for 10 seconds.', 'Delete',
                                  lambda: self.delete_traveler(tid)), color=RED))
            panel.add_widget(row)
            self.body.add_widget(panel)


    def show_traveler_shares(self, traveler_id):
        """Render one active traveler's cost responsibility and expense links."""
        traveler = self.store.get_traveler(self.trip_id, traveler_id)
        if not traveler:
            self.show_detail(self.trip_id, 'travelers')
            return
        self.page = 'traveler_detail'
        self.layout(traveler['name'], lambda: self.show_detail(self.trip_id, 'travelers'))
        shares = self.store.traveler_shares(self.trip_id, traveler_id)
        self.body.add_widget(text('Total share', size=20, height=36, bold=True))
        self.body.add_widget(text(money(sum(share['amount_cents'] for share in shares)) + ' USD', size=28, color=BLUE, height=42, bold=True))
        self.body.add_widget(text('Expense shares, not payment tracking.', color=MUTED, size=14))
        if not shares:
            self.body.add_widget(text('No expenses assigned to this traveler yet.', size=14))
        for share in shares:
            panel = Panel(144)
            panel.add_widget(text(share['name'], color=BLACK, bold=True))
            panel.add_widget(text(money(share['amount_cents']) + (' USD / review needed' if share['split_review'] else ' USD'), color=BLACK, size=14))
            panel.add_widget(Action('View expense', lambda eid=share['id']: self.show_expense_detail(eid)))
            self.body.add_widget(panel)


    # Profile drafts, optional local photos, and saving/discarding changes.
    def show_traveler_form(self, traveler_id=None):
        """Build editable profile fields and a photo draft; only name is required."""
        trip = self.store.get(self.trip_id)
        if not trip:
            self.show_saved()
            return
        traveler = self.store.get_traveler(self.trip_id, traveler_id) if traveler_id else None
        if traveler_id and not traveler:
            self.show_detail(self.trip_id, 'travelers')
            return
        self.page, self.traveler_id = 'traveler_form', traveler_id
        self.layout('Edit traveler' if traveler else 'Add a new traveler', self.cancel_traveler_form, form=True)
        self.body.add_widget(text(f"For {trip['name']}", size=14, color=MUTED))
        self.traveler_inputs, self.traveler_original = {}, {}
        for key, caption, hint in [('name', 'Traveler name *', 'Full name'), ('age', 'Age (optional)', 'Enter age'),
                                   ('phone', 'Phone number (optional)', '+1 (555) 123-4567'),
                                   ('email', 'Email (optional)', 'name@example.com'), ('gender', 'Gender (optional)', 'Enter gender')]:
            self.body.add_widget(text(caption, size=14, height=20))
            value = str(traveler[key]) if traveler and traveler[key] is not None else ''
            self.traveler_original[key] = value
            field = self.form_input(key, value, hint)
            self.traveler_inputs[key] = field
            self.body.add_widget(field)
        self.traveler_photo = traveler['image_bytes'] if traveler else None
        self.original_photo = self.traveler_photo
        self.body.add_widget(text('Photo (optional)', size=14, height=20))
        self.photo_preview = Image(size_hint_y=None, height=dp(0))
        self.body.add_widget(self.photo_preview)
        self.photo_status = text('No photo selected. PNG or JPEG, up to 10 MB.', size=12, color=MUTED)
        self.body.add_widget(self.photo_status)
        photo_actions = BoxLayout(size_hint_y=None, height=dp(44))
        photo_actions.add_widget(Action('Choose photo', self.choose_traveler_photo))
        photo_actions.add_widget(Action('Remove photo', self.remove_traveler_photo))
        self.body.add_widget(photo_actions)
        self.traveler_error = text('', color=RED, size=14, height=60)
        self.body.add_widget(self.traveler_error)
        self.body.add_widget(Action('Save traveler', self.save_traveler_form, primary=True))
        self.update_traveler_photo()


    def update_traveler_photo(self):
        """Refresh the in-memory photo preview or show a missing-photo message."""
        self.photo_preview.texture = None
        self.photo_preview.height = dp(0)
        self.photo_status.text = 'No photo selected. PNG or JPEG, up to 10 MB.'
        if self.traveler_photo:
            try:
                self.photo_preview.texture = self.photo_texture(self.traveler_photo)
                self.photo_preview.height = dp(112)
                self.photo_status.text = 'Photo selected. Save traveler to keep it.'
            except Exception:
                self.photo_status.text = 'Photo unavailable. Choose a replacement or remove it.'


    def remove_traveler_photo(self):
        """Clear the photo draft; storage changes only after Save traveler."""
        self.traveler_photo = None
        self.update_traveler_photo()


    def choose_traveler_photo(self):
        """Open a local file-picker popup; Cancel leaves the existing draft intact."""
        body = BoxLayout(orientation='vertical', spacing=dp(8), padding=dp(8))
        chooser = FileChooserListView(path=str(Path.home()), filters=['*.png', '*.jpg', '*.jpeg', '*.PNG', '*.JPG', '*.JPEG'])
        body.add_widget(chooser)
        message = text('Choose a PNG or JPEG photo.', size=13, height=40)
        body.add_widget(message)
        popup = Popup(title='Choose traveler photo', content=body, size_hint=(.95, .9))
        row = BoxLayout(size_hint_y=None, height=dp(44))
        row.add_widget(Action('Cancel', popup.dismiss))
        def select():
            if not chooser.selection:
                message.text = 'Select a photo first.'
                return
            if self.select_traveler_photo(chooser.selection[0]):
                popup.dismiss()
            else:
                message.text = self.traveler_error.text
        row.add_widget(Action('Use photo', select, primary=True))
        body.add_widget(row)
        self.photo_picker, self.photo_chooser = popup, chooser
        popup.open()


    def select_traveler_photo(self, path):
        """Read/decode a limited-size local file into the draft; return success.

        Reading MAX_PHOTO_BYTES + 1 detects oversized files without loading
        their full contents. Original paths are not persisted in profiles.
        """
        try:
            with open(path, 'rb') as photo:
                data = photo.read(MAX_PHOTO_BYTES + 1)
            if len(data) > MAX_PHOTO_BYTES:
                raise ValueError('Choose a photo smaller than 10 MB.')
            self.photo_texture(data)  # Reject unsupported or undecodable files before saving.
        except Exception:
            self.traveler_error.text = 'Choose a readable PNG or JPEG photo smaller than 10 MB.'
            return False
        self.traveler_photo = data
        self.traveler_error.text = ''
        self.update_traveler_photo()
        return True


    def cancel_traveler_form(self):
        """Confirm discarding changed profile text or photo bytes before returning."""
        def go_back():
            self.show_detail(self.trip_id, 'travelers')
        changed = any(field.text != self.traveler_original[key] for key, field in self.traveler_inputs.items())
        if changed or self.traveler_photo != self.original_photo:
            self.confirm('Discard changes?', 'Your unsaved traveler changes will be lost.', 'Discard', go_back)
        else:
            go_back()


    def save_traveler_form(self):
        """Save validated profile/photo data and offer split review after additions."""
        adding = self.traveler_id is None
        try:
            traveler = validate_traveler(**{key: field.text for key, field in self.traveler_inputs.items()},
                                         image_bytes=self.traveler_photo)
            self.store.save_traveler(self.trip_id, traveler, self.traveler_id)
        except (ValueError, sqlite3.Error, OSError) as error:
            self.traveler_error.text = str(error) if isinstance(error, ValueError) else "Couldn't save this traveler. Please try again."
            self.scroller.scroll_y = 0
            return
        self.show_detail(self.trip_id, 'travelers')
        if adding:
            count = sum(bool(expense['split_review']) for expense in self.store.expenses(self.trip_id))
            if count:
                self.confirm('Review expense splits', f'Traveler saved. {count} expense splits need review.\nSaved amounts have not changed.',
                             'Review', lambda: self.show_detail(self.trip_id, 'expenses'), cancel_caption='Later')


    def delete_traveler(self, traveler_id):
        """Remove a confirmed profile and redraw; storage preserves its expense shares."""
        try:
            self.begin_delete('travelers', traveler_id)
        except (sqlite3.Error, OSError):
            self.confirm("Couldn't delete traveler", 'Please try again.', 'OK', lambda: None)
            return
        self.show_detail(self.trip_id, 'travelers')

