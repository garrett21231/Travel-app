"""Native, offline Trip Planner. Run with the project's Kivy Python environment."""
from pathlib import Path
from io import BytesIO
import sqlite3
from kivy.app import App
from kivy.core.window import Window
from kivy.core.image import Image as CoreImage
from kivy.graphics import Color, RoundedRectangle, Line
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.utils import get_color_from_hex, platform
from trip_store import (TripStore, validate_trip, validate_expense, validate_traveler,
                        photo_format, MAX_PHOTO_BYTES, money, is_past, EXPENSE_CATEGORIES,
                        expense_total_cents, calculate_split)

BLACK, WHITE, BLUE, MUTED, RED = map(get_color_from_hex, ('#000000', '#ffffff', '#6b83ff', '#bdbdbd', '#ff8686'))
ASSETS = Path(__file__).resolve().parent / 'assets'


def text(value, size=16, color=WHITE, height=28, bold=False):
    widget = Label(text=value, font_size=sp(size), color=color, bold=bold,
                   size_hint_y=None, height=dp(height), halign='left', valign='middle',
                   shorten='\n' not in value, shorten_from='right')
    widget.bind(size=lambda w, _: setattr(w, 'text_size', w.size))
    return widget


class Panel(BoxLayout):
    def __init__(self, height, color=WHITE, **kwargs):
        super().__init__(orientation='vertical', padding=dp(14), spacing=dp(8),
                         size_hint_y=None, height=dp(height), **kwargs)
        with self.canvas.before:
            Color(*color)
            self.shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)])
        self.bind(pos=self.update, size=self.update)

    def update(self, *_):
        self.shape.pos, self.shape.size = self.pos, self.size


class Action(Button):
    def __init__(self, caption, callback, primary=False, color=None, **kwargs):
        super().__init__(text=caption, font_size=kwargs.pop('font_size', sp(16)), bold=True,
                         color=color or (BLACK if primary else BLUE),
                         background_normal='', background_down='', background_color=(0, 0, 0, 0),
                         size_hint_y=None, height=dp(44), **kwargs)
        if primary:
            with self.canvas.before:
                self.fill = Color(*BLUE)
                self.shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(7)])
            self.bind(pos=self.update, size=self.update, state=self.update)
        self.bind(on_release=lambda _: callback())

    def update(self, *_):
        self.shape.pos, self.shape.size = self.pos, self.size
        self.fill.rgba = (*BLUE[:3], .7 if self.state == 'down' else 1)

# Outline for the Past Trips button and Overview Box
class OutlineRow(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*WHITE)
            self.outline = Line(rounded_rectangle=(*self.pos, *self.size, dp(14)), width=1)
        self.bind(pos=self.update, size=self.update)

    def update(self, *_):
        self.outline.rounded_rectangle = (*self.pos, *self.size, dp(14))

# Background color for back button, cheveron, and X button
class IconAction(Button):
    def __init__(self, asset, callback):
        super().__init__(background_normal='', background_down='', background_color=(0, 0, 0, 0),
                         size_hint=(None, None), size=(dp(44), dp(44)))
        self.icon = Image(source=str(ASSETS / asset), size_hint=(None, None))
        self.add_widget(self.icon)
        self.bind(pos=self.update, size=self.update, on_release=lambda _: callback())
        self.update()

    def update(self, *_):
        self.icon.size = self.icon.texture_size
        self.icon.center = self.center


class TripPlannerApp(App):
    title = 'Trip Planner'

    def __init__(self, database_path=None, **kwargs):
        super().__init__(**kwargs)
        self.database_path = database_path
        self.page = 'home'
        self.trip_id = None

    def build(self):
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

    def keyboard(self, _, key, *args):
        if key == 27 and self.page != 'home':
            if self.page == 'traveler_form':
                self.cancel_traveler_form()
            elif self.page == 'expense_form':
                self.cancel_expense_form()
            elif self.page == 'form':
                self.cancel_form()
            elif self.page == 'expense_detail':
                self.show_detail(self.trip_id, 'expenses')
            elif self.page == 'traveler_detail':
                self.show_detail(self.trip_id, 'travelers')
            else:
                self.show_home()
            return True
        return False

    def layout(self, title, back=None, create=False, form=False):
        self.shell.clear_widgets()
        header = BoxLayout(size_hint_y=None, height=dp(60), padding=[dp(4), dp(8), dp(15), 0])
        header.add_widget(IconAction('close.png' if form else 'back.png', back) if back else Widget())
        if back:
            header.add_widget(Widget())
        if create:
            header.add_widget(Action('+ Create a trip', self.show_form, size_hint_x=None, width=dp(145)))
        self.shell.add_widget(header)
        self.scroller = ScrollView(do_scroll_x=False)
        self.body = BoxLayout(orientation='vertical', padding=[dp(15), 0, dp(15), dp(24)],
                              spacing=dp(12), size_hint_y=None)
        self.body.bind(minimum_height=self.body.setter('height'))
        self.scroller.add_widget(self.body)
        self.shell.add_widget(self.scroller)
        self.body.add_widget(text(title, size=24, height=40, bold=True))

    def navigation(self, saved=False):
        bar = Panel(62)
        row = BoxLayout()
        row.add_widget(Action('Trips', self.show_home, color=MUTED if saved else BLACK))
        row.add_widget(Action('Saved trips', self.show_saved, color=BLACK if saved else MUTED))
        bar.add_widget(row)
        self.shell.add_widget(bar)

    def empty_card(self, caption):
        panel = Panel(145)
        panel.add_widget(text(caption, color=BLACK, height=66, bold=True))
        panel.add_widget(Action('Create a trip', self.show_form, primary=True, size_hint_x=None, width=dp(125)))
        self.body.add_widget(panel)

    def show_home(self):
        self.page = 'home'
        self.layout('Trips', create=True)
        self.body.add_widget(text('Upcoming', size=20, height=40, bold=True))
        trips = self.store.all()
        upcoming = [t for t in trips if not is_past(t)]
        if not upcoming:
            self.empty_card("You don't have any upcoming trips, looks\nlike it's time to plan your next one!")
        for trip in upcoming:
            self.trip_card(trip)
        self.body.add_widget(Widget(size_hint_y=None, height=dp(18)))
        past = OutlineRow(size_hint_y=None, height=dp(49), padding=[dp(14), 0])
        past_button = Action('Past trips', lambda: self.show_saved(True), color=WHITE, halign='left', valign='middle')
        past_button.bind(size=lambda w, _: setattr(w, 'text_size', w.size))
        past.add_widget(past_button)
        past.add_widget(IconAction('chevron.png', lambda: self.show_saved(True)))
        self.body.add_widget(past)
        self.body.add_widget(Action(f'All saved trips ({len(trips)})  >', self.show_saved))
        self.navigation()

    def show_saved(self, past_only=False):
        self.page, self.past_only = 'saved', past_only
        self.layout('Past trips' if past_only else 'Saved trips', self.show_home, create=True)
        trips = [t for t in self.store.all() if not past_only or is_past(t)]
        self.body.add_widget(text(f"{len(trips)} {'trip' if len(trips) == 1 else 'trips'} saved on this device", color=MUTED))
        if not trips:
            self.empty_card('No past trips yet.' if past_only else 'Your saved trips will appear here.\nPlan your first one to get started.')
        for trip in trips:
            self.trip_card(trip)
        self.navigation(saved=True)

    def trip_card(self, trip):
        button = Button(background_normal='', background_down='', background_color=(0, 0, 0, 0),
                        size_hint_y=None, height=dp(118))
        panel = Panel(118)
        panel.add_widget(text(trip['name'], color=BLACK, bold=True))
        panel.add_widget(text(trip['destination'], size=14, color=BLACK, height=22))
        dates = f"{trip['start_date']} - {trip['end_date']}" if trip['start_date'] else 'Dates not set'
        panel.add_widget(text(f"{dates}\n{money(trip['cost_cents'])} USD  /  {trip['people']} people", size=12, color=BLACK, height=32))
        button.add_widget(panel)
        button.bind(pos=lambda w, _: setattr(panel, 'pos', w.pos), size=lambda w, _: setattr(panel, 'width', w.width))
        button.bind(on_release=lambda _: self.show_detail(trip['id']))
        self.body.add_widget(button)

    def show_form(self, trip_id=None):
        self.form_return = (self.page, getattr(self, 'past_only', False))
        self.page, self.trip_id = 'form', trip_id
        trip = self.store.get(trip_id) if trip_id else None
        self.layout('Edit trip' if trip else 'Create a new trip', self.cancel_form, form=True)
        self.body.add_widget(text('Just the essentials for your next getaway.', size=14, height=24))
        self.inputs = {}
        fields = [('name', 'Trip name *', 'Weekend away'), ('destination', 'Destination *', 'City, place, or address'),
                  ('cost', 'Total estimated cost (USD) *', '0.00'), ('people', 'People going *', 'Including yourself'),
                  ('start_date', 'From date (optional)', 'YYYY-MM-DD'), ('end_date', 'To date (optional)', 'YYYY-MM-DD'),
                  ('description', 'Description (optional)', 'Add a description')]
        self.original = {}
        for key, caption, hint in fields:
            self.body.add_widget(text(caption, size=14, height=20))
            value = (f"{trip['cost_cents'] // 100}.{trip['cost_cents'] % 100:02}" if key == 'cost'
                     else str(trip[key])) if trip else ('1' if key == 'people' else '')
            self.original[key] = value
            field = self.form_input(key, value, hint)
            self.inputs[key] = field
            self.body.add_widget(field)
        self.preview = text('', color=BLUE, height=30)
        self.body.add_widget(self.preview)
        for key in ('cost', 'people'):
            self.inputs[key].bind(text=self.update_preview)
        self.update_preview()
        self.error = text('', color=RED, size=14, height=60)
        self.body.add_widget(self.error)
        self.body.add_widget(Action('Save trip', self.save_form, primary=True))

    def update_preview(self, *_):
        try:
            trip = validate_trip('preview', 'preview', self.inputs['cost'].text, self.inputs['people'].text)
            self.preview.text = f"About {money(trip['cost_cents'], trip['people'])} USD per person"
        except ValueError:
            self.preview.text = 'Enter cost and people to see the split.'

    def cancel_form(self):
        def go_back():
            if self.trip_id:
                self.show_detail(self.trip_id)
            elif self.form_return[0] == 'saved':
                self.show_saved(self.form_return[1])
            else:
                self.show_home()
        if any(field.text != self.original[key] for key, field in self.inputs.items()):
            self.confirm('Discard changes?', 'Your unsaved changes will be lost.', 'Discard', go_back)
        else:
            go_back()

    def save_form(self):
        try:
            trip = validate_trip(**{key: field.text for key, field in self.inputs.items()})
            trip_id = self.store.save(trip, self.trip_id)
        except (ValueError, sqlite3.Error, OSError) as error:
            self.error.text = str(error) if isinstance(error, ValueError) else "Couldn't save this trip. Please try again."
            self.scroller.scroll_y = 0
            return
        self.show_detail(trip_id)

    def form_input(self, key, value, hint):
        background = str(ASSETS / ('description.png' if key == 'description' else 'field.png'))
        return TextInput(text=value, hint_text=hint, multiline=key == 'description',
                         size_hint_y=None, height=dp(127 if key == 'description' else 49),
                         font_size=sp(16), foreground_color=WHITE, hint_text_color=MUTED,
                         cursor_color=BLUE, background_color=WHITE, background_normal=background,
                         background_active=background, border=(15, 15, 15, 15),
                         padding=[dp(18), dp(14)], write_tab=False)

    def show_detail(self, trip_id, tab='overview'):
        self.page, self.trip_id = 'detail', trip_id
        self.detail_tab = tab
        trip = self.store.get(trip_id)
        if not trip:
            self.show_saved()
            return
        self.layout(trip['name'], self.show_saved)
        self.body.add_widget(text('Past trip' if is_past(trip) else 'Your trip plan', color=BLUE))
        expenses = self.store.expenses(trip_id)
        travelers = self.store.travelers(trip_id)
        total = sum(expense_total_cents(expense, trip['people']) for expense in expenses)
        tabs = OutlineRow(size_hint_y=None, height=dp(49), padding=[dp(4), 0])
        tabs.add_widget(Action('Overview', lambda: self.show_detail(trip_id), font_size=sp(13), color=BLUE if tab == 'overview' else MUTED))
        tabs.add_widget(Action(f'Expenses ({len(expenses)})', lambda: self.show_detail(trip_id, 'expenses'),
                               font_size=sp(13), color=BLUE if tab == 'expenses' else MUTED))
        tabs.add_widget(Action(f'Travelers ({len(travelers)})', lambda: self.show_detail(trip_id, 'travelers'),
                               font_size=sp(13), color=BLUE if tab == 'travelers' else MUTED))
        self.body.add_widget(tabs)
        if tab == 'expenses':
            self.show_expenses(trip, expenses, total)
            return
        if tab == 'travelers':
            self.show_travelers(trip, travelers)
            return
        panel = Panel(300)
        for caption, value in [('Destination', trip['destination']), ('From date', trip['start_date'] or 'Not set'),
                               ('To date', trip['end_date'] or 'Not set'), ('Trip estimate', money(trip['cost_cents']) + ' USD'),
                               ('People going', str(trip['people']))]:
            row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            caption_widget = text(caption, size=12, color=BLACK, height=46)
            caption_widget.size_hint_x = .35
            row.add_widget(caption_widget)
            row.add_widget(text(value, size=14, color=BLACK, height=46))
            panel.add_widget(row)
        self.body.add_widget(panel)
        self.body.add_widget(text('Expenses total', size=20, bold=True, height=36))
        self.body.add_widget(text(money(total) + ' USD', size=24, color=BLUE, height=38, bold=True))
        self.body.add_widget(text('Estimated cost per person', size=20, bold=True, height=36))
        self.body.add_widget(text(money(trip['cost_cents'], trip['people']) + ' USD', size=28, color=BLUE, height=42, bold=True))
        self.body.add_widget(text('Estimated equal split, rounded to the nearest cent.', size=12, color=MUTED))
        self.body.add_widget(text('Description', size=20, height=38, bold=True))
        notes = text(trip['description'] or 'No description added.', size=15, height=40)
        notes.shorten = False
        notes.bind(width=lambda w, _: setattr(w, 'text_size', (w.width, None)),
                   texture_size=lambda w, value: setattr(w, 'height', max(dp(40), value[1])))
        self.body.add_widget(notes)
        self.body.add_widget(Action('Edit trip', lambda: self.show_form(trip_id), primary=True))
        self.body.add_widget(Action('Delete trip', lambda: self.confirm('Delete trip?', 'This permanently removes this saved trip.',
                                 'Delete', lambda: self.delete_trip(trip_id)), color=RED))

    def show_expenses(self, trip, expenses, total):
        self.body.add_widget(text('Expenses total', size=20, bold=True, height=36))
        self.body.add_widget(text(money(total) + ' USD', size=28, color=BLUE, height=42, bold=True))
        self.body.add_widget(text(f"Trip average: {money(total, trip['people'])} USD per person", color=MUTED, size=14))
        review = sum(bool(expense['split_review']) for expense in expenses)
        if review:
            self.body.add_widget(text(f'{review} expense splits need review.\nOpen their details to check who shares them.', color=RED, size=14, height=48))
        self.body.add_widget(Action('+ New expense', self.show_expense_form, primary=True))
        if expenses:
            self.body.add_widget(text('By category', size=18, bold=True, height=30))
            for category in EXPENSE_CATEGORIES:
                members = [expense for expense in expenses if expense['category'] == category]
                if members:
                    subtotal = sum(expense_total_cents(expense, trip['people']) for expense in members)
                    self.body.add_widget(text(f'{category}: {money(subtotal)} USD', size=14, color=MUTED))
        if not expenses:
            panel = Panel(104)
            panel.add_widget(text("You don't have any expenses for this trip.\nAdd a flight, hotel, or anything else above.",
                                  color=BLACK, height=76, bold=True))
            self.body.add_widget(panel)
        for expense in expenses:
            panel = Panel(288)
            panel.add_widget(text(expense['name'], color=BLACK, bold=True))
            panel.add_widget(text(expense['category'], color=BLACK, size=13, height=20))
            panel.add_widget(text(money(expense_total_cents(expense, trip['people'])) + ' USD total', color=BLACK, height=24))
            summary = f"{money(expense['cost_cents'])} per person x {expense['split_count']}" if expense['cost_basis'] == 'per_person' else 'Group total'
            panel.add_widget(text(summary + '\n' + ' / '.join(value for value in (expense['expense_date'], expense['provider']) if value),
                                  color=BLACK, size=12, height=36))
            panel.add_widget(text('Split needs review' if expense['split_review'] else
                                  {'everyone': 'Everyone', 'selected': 'Selected travelers', 'custom': 'Custom amounts'}[expense['split_mode']],
                                  color=(.65, .1, .1, 1) if expense['split_review'] else BLACK, size=13, height=20))
            actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
            expense_id = expense['id']
            panel.add_widget(Action('View details', lambda eid=expense_id: self.show_expense_detail(eid)))
            actions.add_widget(Action('Edit expense', lambda eid=expense_id: self.show_expense_form(eid)))
            actions.add_widget(Action('Delete', lambda eid=expense_id: self.confirm('Delete expense?',
                                      'This removes the expense from this trip.', 'Delete',
                                      lambda: self.delete_expense(eid)), color=RED))
            panel.add_widget(actions)
            self.body.add_widget(panel)

    def show_expense_detail(self, expense_id):
        expense = self.store.get_expense(self.trip_id, expense_id)
        if not expense:
            self.show_detail(self.trip_id, 'expenses')
            return
        self.page = 'expense_detail'
        self.layout(expense['name'], lambda: self.show_detail(self.trip_id, 'expenses'))
        trip = self.store.get(self.trip_id)
        self.body.add_widget(text(expense['category'], color=BLUE))
        self.body.add_widget(text(money(expense_total_cents(expense, trip['people'])) + ' USD total', size=28, color=BLUE, height=42, bold=True))
        self.body.add_widget(text(f"{money(expense['cost_cents'])} USD per person x {expense['split_count']} people" if expense['cost_basis'] == 'per_person'
                                  else 'Cost entered for the whole group', size=14, color=MUTED))
        self.body.add_widget(text('Who shares this expense?', size=20, height=36, bold=True))
        if expense['split_review']:
            self.body.add_widget(text('Travelers changed or shares are unassigned.\nEdit this expense to review and save its split.', size=14, color=RED, height=48))
        shares = self.store.expense_shares(self.trip_id, expense_id)
        for share in shares:
            suffix = ' (removed)' if share['traveler_id'] is None else ''
            self.body.add_widget(text(f"{share['name']}{suffix}: {money(share['amount_cents'])} USD", size=15, height=32))
        if not shares:
            self.body.add_widget(text('No named shares yet. Add travelers, then edit\nthis expense to assign its saved total.', size=14, color=MUTED, height=48))
        labels = dict(expense_date='Date', provider='Place / provider', airline='Airline', flight_number='Flight number',
                      departure_airport='Departure airport', arrival_airport='Arrival airport', departure_at='Departure (local time)',
                      arrival_at='Arrival (local time)', check_in='Check-in', check_out='Check-out')
        for key, caption in labels.items():
            if expense[key]:
                self.body.add_widget(text(caption, size=14, color=MUTED, height=22))
                value = text(expense[key], size=16, height=28)
                value.shorten = False
                value.bind(width=lambda w, _: setattr(w, 'text_size', (w.width, None)),
                           texture_size=lambda w, size: setattr(w, 'height', max(dp(28), size[1])))
                self.body.add_widget(value)
        self.body.add_widget(text('Notes', size=20, height=38, bold=True))
        notes = text(expense['description'] or 'No notes added.', size=15, height=40)
        notes.shorten = False
        notes.bind(width=lambda w, _: setattr(w, 'text_size', (w.width, None)),
                   texture_size=lambda w, value: setattr(w, 'height', max(dp(40), value[1])))
        self.body.add_widget(notes)
        self.body.add_widget(Action('Edit expense', lambda: self.show_expense_form(expense_id), primary=True))

    def expense_spinner(self, value, choices):
        return Spinner(text=value, values=choices, size_hint_y=None, height=dp(49),
                       font_size=sp(16), color=WHITE, background_color=WHITE,
                       background_normal=str(ASSETS / 'field.png'), background_down=str(ASSETS / 'field.png'),
                       border=(15, 15, 15, 15))

    def show_expense_form(self, expense_id=None):
        trip = self.store.get(self.trip_id)
        if not trip:
            self.show_saved()
            return
        expense = self.store.get_expense(self.trip_id, expense_id) if expense_id else None
        if expense_id and not expense:
            self.show_detail(self.trip_id, 'expenses')
            return
        self.page, self.expense_id = 'expense_form', expense_id
        self.layout('Edit expense' if expense else 'Create a new expense', self.cancel_expense_form, form=True)
        self.body.add_widget(text(f"For {trip['name']}", size=14, color=MUTED))
        self.expense_inputs, self.expense_original = {}, {}
        self.body.add_widget(text('Category *', size=14, height=20))
        self.expense_category = self.expense_spinner(expense['category'] if expense else 'Other', EXPENSE_CATEGORIES)
        self.body.add_widget(self.expense_category)
        self.body.add_widget(text('How is this cost entered? *', size=14, height=20))
        self.expense_basis = self.expense_spinner('Per person' if expense and expense['cost_basis'] == 'per_person' else 'Group total',
                                                ('Group total', 'Per person'))
        self.body.add_widget(self.expense_basis)
        for key, caption, hint in [('name', 'Expense name *', 'Dinner, taxi, plane flight...'), ('cost', 'Cost (USD) *', '0.00'),
                                   ('expense_date', 'Date (optional)', 'YYYY-MM-DD'),
                                   ('provider', 'Place / provider (optional)', 'Restaurant, taxi company, hotel...')]:
            self.body.add_widget(text(caption, size=14, height=20))
            value = (f"{expense['cost_cents'] // 100}.{expense['cost_cents'] % 100:02}" if key == 'cost'
                     else expense[key]) if expense else ''
            field = self.form_input(key, value, hint)
            self.expense_inputs[key] = field
            self.expense_original[key] = value
            self.body.add_widget(field)
        self.body.add_widget(text('Who shares this expense? *', size=16, bold=True, height=30))
        modes = {'everyone': 'Everyone', 'selected': 'Selected travelers', 'custom': 'Custom amounts'}
        self.expense_split_mode = self.expense_spinner(modes[expense['split_mode']] if expense else 'Everyone', tuple(modes.values()))
        self.body.add_widget(self.expense_split_mode)
        self.split_travelers = self.store.travelers(self.trip_id)
        saved_shares = {share['traveler_id']: share for share in self.store.expense_shares(self.trip_id, expense_id)} if expense else {}
        self.split_rows = {}
        for traveler in self.split_travelers:
            tid = traveler['id']
            row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(6))
            check = CheckBox(active=tid in saved_shares if expense and saved_shares else True,
                             size_hint_x=None, width=dp(38), color=BLUE)
            caption = text(traveler['name'], size=14, height=56)
            amount = self.form_input('amount', f"{saved_shares[tid]['amount_cents'] / 100:.2f}" if tid in saved_shares else '', '0.00')
            amount.size_hint_x, amount.width = None, dp(100)
            row.add_widget(check)
            row.add_widget(caption)
            row.add_widget(amount)
            self.split_rows[tid] = (row, check, amount)
        self.split_container = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(6))
        self.split_container.bind(minimum_height=self.split_container.setter('height'))
        self.body.add_widget(self.split_container)
        self.split_hint = text('', color=MUTED, size=12, height=48)
        self.split_hint.shorten = False
        self.body.add_widget(self.split_hint)
        self.refresh_expense_split()
        self.expense_split_mode.bind(text=self.refresh_expense_split)
        specific = [('airline', 'Airline', 'Airline name'), ('flight_number', 'Flight number', 'AA123'),
                    ('departure_airport', 'Departure airport', 'Airport or city'), ('arrival_airport', 'Arrival airport', 'Airport or city'),
                    ('departure_at', 'Departure date & time', 'YYYY-MM-DD HH:MM'), ('arrival_at', 'Arrival date & time', 'YYYY-MM-DD HH:MM'),
                    ('check_in', 'Check-in date', 'YYYY-MM-DD'), ('check_out', 'Check-out date', 'YYYY-MM-DD')]
        self.expense_specific_widgets = {}
        for key, caption, hint in specific:
            self.expense_inputs[key] = self.form_input(key, expense[key] if expense else '', hint)
            self.expense_specific_widgets[key] = text(caption + ' (optional)', size=14, height=20)
        self.expense_specific = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(12))
        self.expense_specific.bind(minimum_height=self.expense_specific.setter('height'))
        self.body.add_widget(self.expense_specific)
        self.refresh_expense_specific()
        self.expense_category.bind(text=self.refresh_expense_specific)
        self.body.add_widget(text('Notes (optional)', size=14, height=20))
        self.expense_inputs['description'] = self.form_input('description', expense['description'] if expense else '', 'Add notes')
        self.body.add_widget(self.expense_inputs['description'])
        self.expense_preview = text('', size=14, color=BLUE, height=56)
        self.expense_preview.shorten = False
        self.body.add_widget(self.expense_preview)
        self.expense_inputs['cost'].bind(text=self.update_expense_preview)
        self.expense_basis.bind(text=self.update_expense_preview)
        self.expense_split_mode.bind(text=self.update_expense_preview)
        for _, check, amount in self.split_rows.values():
            check.bind(active=self.update_expense_preview)
            amount.bind(text=self.update_expense_preview)
        self.update_expense_preview()
        self.expense_original = self.expense_form_values()
        self.original_split = self.split_form_values()
        self.expense_error = text('', color=RED, size=14, height=60)
        self.body.add_widget(self.expense_error)
        self.body.add_widget(Action('Save expense', self.save_expense_form, primary=True))

    def refresh_expense_specific(self, *_):
        self.expense_specific.clear_widgets()
        category = self.expense_category.text
        if category == 'Flights':
            keys = ('airline', 'flight_number', 'departure_airport', 'arrival_airport', 'departure_at', 'arrival_at')
            self.expense_specific.add_widget(text('Flight details', size=18, bold=True, height=30))
            self.expense_specific.add_widget(text('Use local time at each airport (24-hour time).', size=12, color=MUTED))
        elif category == 'Lodging':
            keys = ('check_in', 'check_out')
            self.expense_specific.add_widget(text('Stay details', size=18, bold=True, height=30))
        else:
            keys = ()
        for key in keys:
            self.expense_specific.add_widget(self.expense_specific_widgets[key])
            self.expense_specific.add_widget(self.expense_inputs[key])

    def expense_form_values(self):
        return dict(**{key: field.text for key, field in self.expense_inputs.items()},
                    category=self.expense_category.text, cost_basis='per_person' if self.expense_basis.text == 'Per person' else 'group',
                    split_mode={'Everyone': 'everyone', 'Selected travelers': 'selected', 'Custom amounts': 'custom'}[self.expense_split_mode.text])

    def split_form_values(self):
        ids = [tid for tid, (_, check, _) in self.split_rows.items() if check.active]
        amounts = {tid: amount.text for tid, (_, check, amount) in self.split_rows.items() if check.active}
        return ids, amounts

    def refresh_expense_split(self, *_):
        self.split_container.clear_widgets()
        mode = self.expense_split_mode.text
        for row, check, amount in self.split_rows.values():
            if mode == 'Everyone':
                check.active = True
            check.disabled = mode == 'Everyone'
            if amount.parent:
                row.remove_widget(amount)
            if mode == 'Custom amounts':
                row.add_widget(amount)
            self.split_container.add_widget(row)
        if not self.split_rows:
            self.split_hint.text = 'Add traveler profiles to choose individual shares.\nEveryone uses the planned headcount for now.'
        elif mode == 'Everyone':
            self.split_hint.text = 'Saving splits across all currently added travelers.\nSaved shares stay fixed until you edit the expense.'
        elif mode == 'Custom amounts':
            self.split_hint.text = 'Check who shares it and enter their amounts.\nUse 0 for no charge; shares must match the total.'
        else:
            self.split_hint.text = 'Check only the travelers who share this expense.\nOthers pay nothing toward it.'

    def update_expense_preview(self, *_):
        try:
            expense = validate_expense('Preview', self.expense_inputs['cost'].text,
                                      cost_basis='per_person' if self.expense_basis.text == 'Per person' else 'group',
                                      split_mode=self.expense_form_values()['split_mode'])
            people = self.store.get(self.trip_id)['people']
            ids, amounts = self.split_form_values()
            count, shares = calculate_split(expense, people, self.split_travelers, ids, amounts)
            total = expense_total_cents(dict(expense, split_count=count), people)
            self.expense_preview.text = f"Group total: {money(total)} USD\n{count} people share this expense"
        except ValueError as error:
            self.expense_preview.text = str(error)

    def cancel_expense_form(self):
        def go_back():
            self.show_detail(self.trip_id, 'expenses')
        if self.expense_form_values() != self.expense_original or self.split_form_values() != self.original_split:
            self.confirm('Discard changes?', 'Your unsaved expense changes will be lost.', 'Discard', go_back)
        else:
            go_back()

    def save_expense_form(self):
        try:
            expense = validate_expense(**self.expense_form_values())
            ids, amounts = self.split_form_values()
            self.store.save_expense(self.trip_id, expense, self.expense_id, ids,
                                   amounts if expense['split_mode'] == 'custom' else None)
        except (ValueError, sqlite3.Error, OSError) as error:
            self.expense_error.text = str(error) if isinstance(error, ValueError) else "Couldn't save this expense. Please try again."
            self.scroller.scroll_y = 0
            return
        self.show_detail(self.trip_id, 'expenses')

    def delete_expense(self, expense_id):
        try:
            self.store.delete_expense(self.trip_id, expense_id)
        except (sqlite3.Error, OSError):
            self.confirm("Couldn't delete expense", 'Please try again.', 'OK', lambda: None)
            return
        self.show_detail(self.trip_id, 'expenses')

    def photo_texture(self, data):
        # Load the saved bytes, not a path to the user's original photo.
        return CoreImage(BytesIO(data), ext=photo_format(data)).texture

    def show_travelers(self, trip, travelers):
        self.body.add_widget(text(f"{len(travelers)} added / {trip['people']} people planned", color=MUTED, size=14))
        if any(expense['split_review'] for expense in self.store.expenses(self.trip_id)):
            self.body.add_widget(Action('Review expense splits', lambda: self.show_detail(self.trip_id, 'expenses')))
        self.body.add_widget(Action('+ New traveler', self.show_traveler_form, primary=True))
        if not travelers:
            panel = Panel(104)
            panel.add_widget(text('No travelers added yet.\nAdd the people going on your trip above.', color=BLACK, height=76, bold=True))
            self.body.add_widget(panel)
        for traveler in travelers:
            panel = Panel(416 if traveler['image_bytes'] else 312)
            if traveler['image_bytes']:
                try:
                    panel.add_widget(Image(texture=self.photo_texture(traveler['image_bytes']), size_hint_y=None, height=dp(96)))
                except Exception:
                    panel.add_widget(text('Photo unavailable', color=BLACK, height=96))
            panel.add_widget(text(traveler['name'], color=BLACK, bold=True))
            age = str(traveler['age']) if traveler['age'] is not None else 'Not set'
            for caption, value in [('Age', age), ('Phone', traveler['phone']), ('Email', traveler['email']), ('Gender', traveler['gender'])]:
                panel.add_widget(text(f"{caption}: {value or 'Not set'}", color=BLACK, size=13, height=20))
            total = sum(share['amount_cents'] for share in self.store.traveler_shares(self.trip_id, traveler['id']))
            panel.add_widget(text(f'Total share: {money(total)} USD', color=BLACK, bold=True, height=24))
            panel.add_widget(Action('View shares', lambda tid=traveler['id']: self.show_traveler_shares(tid)))
            row = BoxLayout(size_hint_y=None, height=dp(44))
            traveler_id = traveler['id']
            row.add_widget(Action('Edit traveler', lambda tid=traveler_id: self.show_traveler_form(tid)))
            row.add_widget(Action('Delete', lambda tid=traveler_id: self.confirm('Delete traveler?',
                                  'Their saved expense shares stay unchanged.\nAffected expenses will need review.', 'Delete',
                                  lambda: self.delete_traveler(tid)), color=RED))
            panel.add_widget(row)
            self.body.add_widget(panel)

    def show_traveler_shares(self, traveler_id):
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

    def show_traveler_form(self, traveler_id=None):
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
        self.traveler_photo = None
        self.update_traveler_photo()

    def choose_traveler_photo(self):
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
        def go_back():
            self.show_detail(self.trip_id, 'travelers')
        changed = any(field.text != self.traveler_original[key] for key, field in self.traveler_inputs.items())
        if changed or self.traveler_photo != self.original_photo:
            self.confirm('Discard changes?', 'Your unsaved traveler changes will be lost.', 'Discard', go_back)
        else:
            go_back()

    def save_traveler_form(self):
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
        try:
            self.store.delete_traveler(self.trip_id, traveler_id)
        except (sqlite3.Error, OSError):
            self.confirm("Couldn't delete traveler", 'Please try again.', 'OK', lambda: None)
            return
        self.show_detail(self.trip_id, 'travelers')

    def delete_trip(self, trip_id):
        try:
            self.store.delete(trip_id)
        except (sqlite3.Error, OSError):
            self.confirm("Couldn't delete trip", 'Please try again.', 'OK', lambda: None)
            return
        self.show_saved()

    def confirm(self, title, message, action, callback, cancel_caption='Cancel'):
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


if __name__ == '__main__':
    TripPlannerApp().run()
