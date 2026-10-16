"""Shared page layout, bottom navigation, Back routing, and form inputs."""
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from date_picker import DateField
from trip_ui.theme import BLACK, WHITE, BLUE, MUTED, ASSETS
from trip_ui.widgets import text, Panel, Action, IconAction


class NavigationMixin:
    """Shared page layout, bottom navigation, Back routing, and form inputs.

    Mixed into TripPlannerApp; self is the one running app, not a separate
    screen instance. Shared state is documented in docs/CODE_GUIDE.md.
    """

    def keyboard(self, _, key, *args):
        """Route Escape/Back by page; return True when the app consumes the event."""
        if key == 27 and self.selection_page == self.page:
            self.end_trip_selection()
            return True
        if key == 27:
            for widget in self.shell.walk():
                if isinstance(widget, DateField) and hasattr(widget, 'calendar_menu') and widget.calendar_menu.parent:
                    widget.calendar_menu.dismiss()
                    return True
        if key == 27 and self.page != 'home':
            if self.page == 'traveler_form':
                self.cancel_traveler_form()
            elif self.page == 'expense_form':
                self.cancel_expense_form()
            elif self.page == 'form':
                self.cancel_form()
            elif self.page == 'notes':
                self.cancel_notes()
            elif self.page == 'expense_detail':
                self.show_detail(self.trip_id, 'expenses')
            elif self.page == 'traveler_detail':
                self.show_detail(self.trip_id, 'travelers')
            else:
                self.show_home()
            return True
        return False


    def layout(self, title, back=None, form=False, more=None, select=False):
        """Replace the page with a header and scrolling vertical body.

        back is a callback for the header icon; form selects the close icon.
        more opens contextual tools; select adds the list-selection action.
        Callers append page widgets
        to self.body and optionally add a footer with navigation().
        """
        self.shell.clear_widgets()
        header = BoxLayout(size_hint_y=None, height=dp(60), padding=[dp(4), dp(8), dp(15), 0])
        header.add_widget(IconAction('close.png' if form else 'back.png', back) if back else Widget())
        if back:
            header.add_widget(Widget())
        if select:
            selecting = self.selection_page == self.page
            header.add_widget(Action('Cancel' if selecting else 'Select',
                                    self.end_trip_selection if selecting else self.start_trip_selection,
                                    size_hint_x=None, width=dp(75)))
        if more:
            header.add_widget(Action('More', more, size_hint_x=None, width=dp(80)))
        self.shell.add_widget(header)
        self.scroller = ScrollView(do_scroll_x=False)
        self.body = BoxLayout(orientation='vertical', padding=[dp(15), 0, dp(15), dp(24)],
                              spacing=dp(12), size_hint_y=None)
        self.body.bind(minimum_height=self.body.setter('height'))
        # The body grows with its children instead of stretching to the window;
        # ScrollView can then scroll longer forms on small displays.
        self.scroller.add_widget(self.body)
        self.shell.add_widget(self.scroller)
        self.body.add_widget(text(title, size=24, height=40, bold=True))
        self.attach_undo()


    def navigation(self, selected='trips'):
        """Highlight the current destination with the same fill as trip tabs."""
        bar = Panel(76)
        row = BoxLayout(spacing=dp(6))
        for key, caption, callback in [('trips', 'Upcoming', self.show_home),
                                       ('saved', 'All trips', self.show_saved),
                                       ('settings', 'Settings', self.show_settings)]:
            row.add_widget(Action(caption, callback, primary=selected == key, font_size=sp(14),
                                  color=BLACK if selected == key else (.3, .3, .3, 1)))
        bar.add_widget(row)
        self.shell.add_widget(bar)


    def empty_card(self, caption):
        """Show an empty list message below the page's New trip action."""
        panel = Panel(104)
        panel.add_widget(text(caption, color=BLACK, height=66, bold=True))
        self.body.add_widget(panel)


    def form_input(self, key, value, hint):
        """Create shared inputs; date fields expose ISO text through a calendar."""
        background = str(ASSETS / ('description.png' if key == 'description' else 'field.png'))
        if key in ('start_date', 'end_date', 'expense_date', 'check_in', 'check_out', 'departure_at', 'arrival_at'):
            return DateField(value=value, with_time=key in ('departure_at', 'arrival_at'), background=background, accent=BLUE)
        return TextInput(text=value, hint_text=hint, multiline=key in ('description', 'destination'),
                         size_hint_y=None, height=dp(127 if key == 'description' else 90 if key == 'destination' else 49),
                         font_size=sp(16), foreground_color=WHITE, hint_text_color=MUTED,
                         cursor_color=BLUE, background_color=WHITE, background_normal=background,
                         background_active=background, border=(15, 15, 15, 15),
                         padding=[dp(18), dp(14)], write_tab=False)

