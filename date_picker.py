"""Calendar dropdowns that display friendly dates and keep ISO form values.

DateField.text follows the same draft-value interface as TextInput, so existing
form validation and save/discard logic can read it unchanged. No date strings
are migrated in the database. Flight fields include a separate 24-hour time.
"""
import calendar
from datetime import date
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.properties import StringProperty
from kivy.graphics import Color, RoundedRectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from trip_store import MONTH_NAMES, display_date


class DateField(BoxLayout):
    """An optional date button, with a time input when with_time=True."""
    text = StringProperty('')

    def __init__(self, value='', with_time=False, background='', accent=(.42, .51, 1, 1), **kwargs):
        super().__init__(size_hint_y=None, height=dp(49), spacing=dp(8), **kwargs)
        self.with_time, self.accent = with_time, accent
        self._syncing = False
        self.date_button = Button(text='Choose date', color=(1, 1, 1, 1), font_size=sp(15),
                                  background_normal=background, background_down=background,
                                  background_color=(1, 1, 1, 1), border=(15, 15, 15, 15))
        self.date_button.bind(on_release=self.open_calendar)
        self.add_widget(self.date_button)
        if with_time:
            self.time_input = TextInput(text='00:00', hint_text='HH:MM', multiline=False, write_tab=False,
                                        size_hint_x=None, width=dp(88), font_size=sp(15),
                                        foreground_color=(1, 1, 1, 1), cursor_color=accent,
                                        background_normal=background, background_active=background,
                                        background_color=(1, 1, 1, 1), border=(15, 15, 15, 15), padding=[dp(10), dp(14)])
            self.time_input.bind(text=self.time_changed)
            self.add_widget(self.time_input)
        self.bind(text=self.refresh_display)
        Window.bind(size=self.resize_calendar)
        self.text = value
        self.refresh_display()

    def refresh_display(self, *_):
        """Update the visible label/time when the canonical draft changes."""
        self._syncing = True
        try:
            self.date_button.text = display_date(self.text.split(' ')[0]) if self.text else 'Choose date  v'
        except ValueError:
            self.date_button.text = 'Choose date  v'
        if self.with_time:
            self.time_input.text = self.text.partition(' ')[2] or '00:00'
        self._syncing = False

    def time_changed(self, *_):
        """Keep the chosen date and draft time together for normal validation."""
        if not self._syncing and self.text:
            self.text = self.text.split(' ')[0] + ' ' + self.time_input.text

    def open_calendar(self, *_):
        """Anchor a month/year calendar to this date button; navigation is a draft."""
        try:
            current = date.fromisoformat(self.text.split(' ')[0]) if self.text else date.today()
        except ValueError:
            current = date.today()
        self.year, self.month = current.year, current.month
        self.calendar_menu = DropDown(auto_width=False, width=min(dp(344), Window.width - dp(30)),
                                      max_height=Window.height - dp(40), dismiss_on_select=False)
        body = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(386), padding=dp(8), spacing=dp(6))
        # The calendar needs an opaque background above the form beneath it.
        with body.canvas.before:
            Color(.06, .06, .06, 1)
            backdrop = RoundedRectangle(pos=body.pos, size=body.size, radius=[dp(10)])
        def place_backdrop(*_):
            backdrop.pos, backdrop.size = body.pos, body.size
        body.bind(pos=place_backdrop, size=place_backdrop)
        header = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        for caption, delta in (('<', -1),):
            button = self.calendar_action(caption, lambda d=delta: self.move_month(d))
            button.size_hint_x, button.width = None, dp(32)
            header.add_widget(button)
        self.month_choice = Spinner(text=MONTH_NAMES[self.month - 1], values=MONTH_NAMES, font_size=sp(15))
        self.year_choice = Spinner(text=str(self.year), values=tuple(str(y) for y in range(min(1900, self.year), max(2100, self.year) + 1)), font_size=sp(15))
        header.add_widget(self.month_choice)
        header.add_widget(self.year_choice)
        next_button = self.calendar_action('>', lambda: self.move_month(1))
        next_button.size_hint_x, next_button.width = None, dp(32)
        header.add_widget(next_button)
        body.add_widget(header)
        weekdays = GridLayout(cols=7, size_hint_y=None, height=dp(28))
        for name in ('Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'):
            weekdays.add_widget(Label(text=name, font_size=sp(12), color=(.74, .74, .74, 1)))
        body.add_widget(weekdays)
        self.days = GridLayout(cols=7, size_hint_y=None, height=dp(236), spacing=dp(4))
        body.add_widget(self.days)
        footer = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        footer.add_widget(self.calendar_action('Clear date', self.clear_date))
        footer.add_widget(self.calendar_action('Cancel', self.calendar_menu.dismiss))
        body.add_widget(footer)
        self.calendar_menu.add_widget(body)
        self.month_choice.bind(text=self.month_selected)
        self.year_choice.bind(text=self.month_selected)
        self.render_days()
        self.calendar_menu.open(self.date_button)

    def resize_calendar(self, *_):
        """Keep an open dropdown inside the viewport after rotation/resizing."""
        if hasattr(self, 'calendar_menu'):
            self.calendar_menu.width = min(dp(344), Window.width - dp(30))
            self.calendar_menu.max_height = Window.height - dp(40)

    def calendar_action(self, caption, callback):
        return Button(text=caption, font_size=sp(14), color=(1, 1, 1, 1), background_normal='',
                      background_color=(.12, .12, .12, 1), on_release=lambda _: callback())

    def move_month(self, delta):
        """Move through months, including December/January and year limits."""
        absolute = self.year * 12 + self.month - 1 + delta
        year, month = divmod(absolute, 12)
        if 1 <= year <= 9999:
            self.year, self.month = year, month + 1
            self.render_days()

    def month_selected(self, *_):
        if not self._syncing:
            self.year = int(self.year_choice.text)
            self.month = MONTH_NAMES.index(self.month_choice.text) + 1
            self.render_days()

    def render_days(self):
        """Render six weeks; blank slots are disabled and selected dates are blue."""
        self._syncing = True
        self.month_choice.text, self.year_choice.text = MONTH_NAMES[self.month - 1], str(self.year)
        self._syncing = False
        self.days.clear_widgets()
        slots = [day for week in calendar.Calendar(firstweekday=6).monthdayscalendar(self.year, self.month) for day in week]
        slots += [0] * (42 - len(slots))
        for day in slots:
            chosen = date(self.year, self.month, day) if day else None
            selected = chosen and self.text.split(' ')[0] == chosen.isoformat()
            button = Button(text=str(day) if day else '', disabled=not day, font_size=sp(14),
                            background_normal='', background_down='', background_color=self.accent if selected else (.1, .1, .1, 1),
                            color=(0, 0, 0, 1) if selected else (1, 1, 1, 1))
            if chosen:
                button.bind(on_release=lambda _, d=chosen: self.select_date(d))
            self.days.add_widget(button)

    def select_date(self, chosen):
        """Commit one date to the form draft, retaining a flight's time component."""
        self.text = chosen.isoformat() + (' ' + self.time_input.text if self.with_time else '')
        self.calendar_menu.dismiss()

    def clear_date(self):
        self.text = ''
        self.calendar_menu.dismiss()
