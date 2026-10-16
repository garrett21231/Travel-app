"""Trip lists, selection, trip forms, overview, and quick notes."""
import sqlite3
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.uix.checkbox import CheckBox
from planning_tools import stage_trip_deletions
from trip_store import validate_trip, money, is_past, expense_total_cents, display_date
from trip_ui.theme import BLACK, WHITE, BLUE, MUTED, RED
from trip_ui.widgets import text, wrapped_text, content_panel, Panel, Action, OutlineRow, IconAction


class TripScreensMixin:
    """Trip lists, selection, trip forms, overview, and quick notes.

    Mixed into TripPlannerApp; self is the one running app, not a separate
    screen instance. Shared state is documented in docs/CODE_GUIDE.md.
    """

    # Trip lists and cards.
    def show_home(self):
        """Render upcoming/undated trips and one link to the full collection."""
        self.prepare_trip_selection('home')
        self.page = 'home'
        trips = self.store.all()
        upcoming = [t for t in trips if not is_past(t)]
        self.layout('Upcoming trips', select=bool(upcoming))
        self.body.add_widget(wrapped_text('Your next trips and plans without dates.', color=MUTED))
        if self.selection_page != self.page:
            self.body.add_widget(Action('+ New trip', self.show_form, primary=True))
        self.trip_selection_controls(upcoming)
        if not upcoming:
            self.empty_card("You don't have any upcoming trips, looks\nlike it's time to plan your next one!")
        for trip in upcoming:
            self.trip_card(trip)
        self.body.add_widget(Widget(size_hint_y=None, height=dp(18)))
        all_trips = OutlineRow(size_hint_y=None, height=dp(49), padding=[dp(14), 0])
        all_button = Action(f'All trips ({len(trips)})', self.show_saved, color=WHITE,
                            halign='left', valign='middle')
        all_button.bind(size=lambda w, _: setattr(w, 'text_size', w.size))
        all_trips.add_widget(all_button)
        all_trips.add_widget(IconAction('chevron.png', self.show_saved))
        self.body.add_widget(all_trips)
        self.navigation()


    def show_saved(self):
        """Group all trips by start year, newest first, with undated trips last.

        ISO dates sort chronologically. Cross-year trips use their start year.
        """
        self.prepare_trip_selection('saved')
        self.page = 'saved'
        self.layout('All trips', self.end_trip_selection if self.selection_page == 'saved' else self.show_home,
                    select=bool(self.store.all()))
        trips = sorted(self.store.all(), key=lambda trip: (trip['start_date'], trip['id']), reverse=True)
        self.trip_selection_controls(trips)
        self.body.add_widget(text(f"{len(trips)} {'trip' if len(trips) == 1 else 'trips'} saved on this device", color=MUTED))
        if self.selection_page != self.page:
            self.body.add_widget(Action('+ New trip', self.show_form, primary=True))
        if not trips:
            self.empty_card('Your saved trips will appear here.\nPlan your first one to get started.')
        last_year = None
        for trip in trips:
            year = trip['start_date'][:4] if trip['start_date'] else 'Dates undecided'
            if year != last_year:
                self.body.add_widget(text(year, size=20, height=40, bold=True))
                last_year = year
            self.trip_card(trip)
        self.navigation(selected='saved')


    def trip_card(self, trip):
        """Append one tappable trip summary; capture its ID in the callback."""
        button = Button(background_normal='', background_down='', background_color=(0, 0, 0, 0),
                        size_hint_y=None, height=dp(118))
        panel = content_panel()
        panel.bind(height=button.setter('height'))
        panel.add_widget(wrapped_text(trip['name'], size=16, color=BLACK, bold=True))
        panel.add_widget(wrapped_text(trip['destination'].replace('\n', ' > ') or 'Destination undecided', color=BLACK, height=22))
        dates = f"{display_date(trip['start_date'])} - {display_date(trip['end_date'])}" if trip['start_date'] else 'Dates not set'
        budget = money(trip['cost_cents']) + ' USD budget' if trip['budget_set'] else 'Budget not set'
        panel.add_widget(wrapped_text(f"{dates}\n{budget} / {trip['people']} people planned", size=12, color=BLACK, height=32))
        button.add_widget(panel)
        button.bind(pos=lambda w, _: setattr(panel, 'pos', w.pos), size=lambda w, _: setattr(panel, 'width', w.width))
        if self.selection_page == self.page:
            row = BoxLayout(size_hint_y=None, height=button.height, spacing=dp(8))
            button.bind(height=row.setter('height'))
            check = CheckBox(active=trip['id'] in self.selected_trip_ids, size_hint_x=None, width=dp(44))
            check.bind(active=lambda _, active: self.toggle_trip_selection(trip['id'], active))
            self.trip_selection_checks[trip['id']] = check
            row.add_widget(check)
            row.add_widget(button)
            button.bind(on_release=lambda _: self.toggle_trip_selection(trip['id']))
            self.body.add_widget(row)
        else:
            button.bind(on_release=lambda _: self.show_detail(trip['id']))
            self.body.add_widget(button)


    # Temporary selection state and confirmed group deletion.
    def prepare_trip_selection(self, page):
        """Leaving a list clears its selection so hidden trips are never deleted."""
        if self.selection_page != page:
            self.selection_page = None
            self.selected_trip_ids.clear()


    def start_trip_selection(self):
        self.selection_page = self.page
        self.selected_trip_ids.clear()
        (self.show_saved if self.page == 'saved' else self.show_home)()


    def end_trip_selection(self):
        self.selection_page = None
        self.selected_trip_ids.clear()
        (self.show_saved if self.page == 'saved' else self.show_home)()


    def trip_selection_controls(self, trips):
        """Pin group actions above the scrolling cards; select only this list."""
        if self.selection_page != self.page:
            return
        self.selectable_trip_ids = {trip['id'] for trip in trips}
        self.selected_trip_ids.intersection_update(self.selectable_trip_ids)
        self.trip_selection_checks = {}
        bar = Panel(100, color=BLACK)
        self.selection_count = text('', size=14)
        bar.add_widget(self.selection_count)
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        self.select_all_action = Action('Select all', self.toggle_all_trips, font_size=sp(14))
        self.delete_selected_action = Action('Delete (0)', self.confirm_trip_selection, color=RED, font_size=sp(14))
        row.add_widget(self.select_all_action)
        row.add_widget(self.delete_selected_action)
        bar.add_widget(row)
        self.shell.add_widget(bar, index=self.shell.children.index(self.scroller) + 1)
        self.update_trip_selection()


    def update_trip_selection(self):
        count = len(self.selected_trip_ids)
        self.selection_count.text = f'{count} selected — tap trips to select'
        self.delete_selected_action.text = f'Delete ({count})'
        self.delete_selected_action.disabled = count == 0
        all_selected = bool(self.selectable_trip_ids) and self.selected_trip_ids == self.selectable_trip_ids
        self.select_all_action.text = 'Deselect all' if all_selected else 'Select all'
        self.select_all_action.disabled = not self.selectable_trip_ids


    def toggle_trip_selection(self, trip_id, active=None):
        if trip_id not in self.selectable_trip_ids:
            return
        active = trip_id not in self.selected_trip_ids if active is None else active
        (self.selected_trip_ids.add if active else self.selected_trip_ids.discard)(trip_id)
        check = self.trip_selection_checks[trip_id]
        if check.active != active:
            check.active = active
        self.update_trip_selection()


    def toggle_all_trips(self):
        active = self.selected_trip_ids != self.selectable_trip_ids
        for trip_id in self.selectable_trip_ids:
            self.toggle_trip_selection(trip_id, active)


    def confirm_trip_selection(self):
        ids = sorted(self.selected_trip_ids)
        if not ids:
            return
        page = self.page
        count = len(ids)
        self.confirm('Delete selected trips?', f"Delete {count} selected {'trip' if count == 1 else 'trips'} and their details?\nUndo is available for 10 seconds.",
                     'Delete', lambda: self.delete_selected_trips(ids, page))


    def delete_selected_trips(self, ids, page):
        """Create one Undo operation for the entire confirmed selection."""
        try:
            self.expire_undo()
            self.undo_token = stage_trip_deletions(self.store, ids)
            self.undo_token['return_page'] = page
            self.undo_event = Clock.schedule_once(self.expire_undo, 10)
        except (ValueError, sqlite3.Error, OSError) as error:
            self.confirm("Couldn't delete trips", str(error) if isinstance(error, ValueError) else 'Please try again.', 'OK', lambda: None)
            return
        self.selection_page = None
        self.selected_trip_ids.clear()
        (self.show_saved if page == 'saved' else self.show_home)()


    # Trip creation/editing: draft, validation, save, and discard.
    def show_form(self, trip_id=None):
        """Build a new/edit trip form and snapshot fields for discard detection."""
        self.form_return = self.page
        self.prepare_trip_selection('form')
        self.page, self.trip_id = 'form', trip_id
        trip = self.store.get(trip_id) if trip_id else None
        self.layout('Edit trip' if trip else 'Create a new trip', self.cancel_form, form=True)
        self.body.add_widget(text('Just the essentials for your next getaway.', size=14, height=24))
        self.inputs = {}
        fields = [('name', 'Trip name *', 'Weekend away'), ('destination', 'Destinations (optional, one stop per line)', 'Boston\nNew York'),
                  ('cost', 'Trip budget (USD, optional)', 'Leave blank if undecided'), ('people', 'People planned (default 1)', 'Including yourself'),
                  ('start_date', 'From date (optional)', 'YYYY-MM-DD'), ('end_date', 'To date (optional)', 'YYYY-MM-DD'),
                  ('description', 'Notes (optional)', 'Ideas, reminders, things to compare...')]
        self.original = {}
        for key, caption, hint in fields:
            self.body.add_widget(text(caption, size=14, height=20))
            value = ((f"{trip['cost_cents'] // 100}.{trip['cost_cents'] % 100:02}" if trip['budget_set'] else '') if key == 'cost'
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
        """Preview the optional budget average without writing anything to storage."""
        try:
            trip = validate_trip('preview', 'preview', self.inputs['cost'].text, self.inputs['people'].text)
            self.preview.text = f"Budget average: {money(trip['cost_cents'], trip['people'])} USD per person" if trip['budget_set'] else 'Budget undecided. You can add it later.'
        except ValueError:
            self.preview.text = 'Enter cost and people to see the split.'


    def cancel_form(self):
        """Return to the originating trip/list, confirming only when fields changed."""
        def go_back():
            if self.trip_id:
                self.show_detail(self.trip_id)
            elif self.form_return == 'saved':
                self.show_saved()
            else:
                self.show_home()
        if any(field.text != self.original[key] for key, field in self.inputs.items()):
            self.confirm('Discard changes?', 'Your unsaved changes will be lost.', 'Discard', go_back)
        else:
            go_back()


    def save_form(self):
        """Validate trip widget strings, save, and open details; show errors inline."""
        try:
            trip = validate_trip(**{key: field.text for key, field in self.inputs.items()})
            trip_id = self.store.save(trip, self.trip_id, create_default_traveler=self.trip_id is None)
        except (ValueError, sqlite3.Error, OSError) as error:
            self.error.text = str(error) if isinstance(error, ValueError) else "Couldn't save this trip. Please try again."
            self.scroller.scroll_y = 0
            return
        self.show_detail(trip_id)


    # Shared trip tabs and the overview/budget page.
    def show_detail(self, trip_id, tab='overview', category_filter=None, review_only=None):
        """Render the trip tabs and dispatch to overview, expenses, or travelers."""
        # Filters are local UI preferences for this trip, not stored trip data.
        if getattr(self, 'filter_trip_id', None) != trip_id:
            self.filter_trip_id = trip_id
            self.expense_filters = ('All categories', False)
        category, review = self.expense_filters
        self.expense_filters = (category if category_filter is None else category_filter,
                                review if review_only is None else review_only)
        self.page, self.trip_id = 'detail', trip_id
        self.detail_tab = tab
        trip = self.store.get(trip_id)
        if not trip:
            self.show_saved()
            return
        self.layout(trip['name'], self.show_saved, more=self.show_trip_tools)
        # Place the title and tabs outside ScrollView, above its content. The
        # same navigation stays available even at the bottom of a long list.
        self.body.clear_widgets()
        heading = BoxLayout(orientation='vertical', padding=[dp(15), 0, dp(15), dp(12)],
                            spacing=dp(6), size_hint_y=None)
        heading.bind(minimum_height=heading.setter('height'))
        heading.add_widget(wrapped_text(trip['name'], size=24, height=36, bold=True))
        heading.add_widget(text('Past trip' if is_past(trip) else 'Your trip plan', color=BLUE, height=24))
        expenses = self.store.expenses(trip_id)
        travelers = self.store.travelers(trip_id)
        total = sum(expense_total_cents(expense, trip['people']) for expense in expenses)
        tabs = OutlineRow(size_hint_y=None, height=dp(52), padding=dp(4), spacing=dp(4))
        tabs.add_widget(Action('Overview', lambda: self.show_detail(trip_id), font_size=sp(13),
                               primary=tab == 'overview', color=BLACK if tab == 'overview' else MUTED))
        tabs.add_widget(Action(f'Expenses ({len(expenses)})', lambda: self.show_detail(trip_id, 'expenses'),
                               font_size=sp(13), primary=tab == 'expenses', color=BLACK if tab == 'expenses' else MUTED))
        tabs.add_widget(Action(f'Travelers ({len(travelers)})', lambda: self.show_detail(trip_id, 'travelers'),
                               font_size=sp(13), primary=tab == 'travelers', color=BLACK if tab == 'travelers' else MUTED))
        heading.add_widget(tabs)
        self.trip_tabs = tabs
        self.shell.add_widget(heading, index=self.shell.children.index(self.scroller) + 1)
        self.body.add_widget(wrapped_text({'overview': 'Trip overview', 'expenses': 'Expenses', 'travelers': 'Travelers'}[tab],
                                          size=22, height=34, bold=True))
        if tab == 'expenses':
            self.show_expenses(trip, expenses, total)
            return
        if tab == 'travelers':
            self.show_travelers(trip, travelers)
            return
        panel = content_panel()
        panel.add_widget(wrapped_text('Destinations: ' + (trip['destination'].replace('\n', ' > ') or 'Undecided'), color=BLACK))
        dates = f"{display_date(trip['start_date'])} – {display_date(trip['end_date'])}" if trip['start_date'] else 'Dates undecided'
        panel.add_widget(wrapped_text(dates, color=BLACK))
        panel.add_widget(wrapped_text(f"{trip['people']} {'person' if trip['people'] == 1 else 'people'} planned", color=BLACK))
        self.body.add_widget(panel)
        budget = content_panel()
        budget.add_widget(wrapped_text('Budget overview', size=18, color=BLACK, bold=True))
        budget.add_widget(wrapped_text('Budget: ' + (money(trip['cost_cents']) + ' USD' if trip['budget_set'] else 'Not set'), color=BLACK))
        budget.add_widget(wrapped_text(f'Planned: {money(total)} USD', size=20, color=BLACK, height=30, bold=True))
        if trip['budget_set']:
            difference = trip['cost_cents'] - total
            budget.add_widget(wrapped_text(f"{'Remaining' if difference >= 0 else 'Over budget'}: {money(abs(difference))} USD",
                                           color=BLACK if difference >= 0 else (.65, .1, .1, 1), bold=True))
        estimated = sum(expense_total_cents(e, trip['people']) for e in expenses if e['cost_status'] == 'estimated')
        budget.add_widget(wrapped_text(f'Estimated: {money(estimated)} USD\nConfirmed: {money(total - estimated)} USD', size=13, color=BLACK))
        self.body.add_widget(budget)
        self.body.add_widget(wrapped_text('Based on expenses added so far.\nConfirmed means known price, not paid.', size=12, color=MUTED))
        self.body.add_widget(text('Cost by traveler', size=20, height=38, bold=True))
        allocated = 0
        for traveler in travelers:
            amount = sum(s['amount_cents'] for s in self.store.traveler_shares(trip_id, traveler['id']))
            allocated += amount
            self.body.add_widget(Action(f"{traveler['name']}: {money(amount)} USD", lambda tid=traveler['id']: self.show_traveler_shares(tid)))
        if allocated != total:
            self.body.add_widget(wrapped_text(f'{money(total - allocated)} USD unassigned or retained for removed travelers.\nReview expense splits before treating personal totals as final.', size=12, color=RED))
        # Show the saved roster (including the default You) before inviting
        # additions, so a new trip never leads this section with an empty CTA.
        self.traveler_progress(trip, travelers)
        self.body.add_widget(text('Notes', size=20, height=38, bold=True))
        notes = text(trip['description'] or 'No description added.', size=15, height=40)
        notes.shorten = False
        notes.bind(width=lambda w, _: setattr(w, 'text_size', (w.width, None)),
                   texture_size=lambda w, value: setattr(w, 'height', max(dp(40), value[1])))
        self.body.add_widget(notes)
        self.body.add_widget(Action('Edit notes', self.show_notes))
        self.body.add_widget(Action('Edit trip', lambda: self.show_form(trip_id), primary=True))
        self.body.add_widget(Action('Duplicate trip', self.show_duplicate))
        self.body.add_widget(Action('Delete trip', lambda: self.confirm('Delete trip?', 'Removes this trip and its details.\nUndo is available for 10 seconds.',
                                 'Delete', lambda: self.delete_trip(trip_id)), color=RED))


    def delete_trip(self, trip_id):
        """Delete a confirmed trip and return to the saved-trip list."""
        try:
            self.begin_delete('trips', trip_id)
        except (sqlite3.Error, OSError):
            self.confirm("Couldn't delete trip", 'Please try again.', 'OK', lambda: None)
            return
        self.show_saved()


    # Quick notes use the existing trip description field.
    def show_notes(self):
        """Quick notes editor independent of the trip's dates and budget."""
        trip = self.store.get(self.trip_id)
        if not trip:
            self.show_saved()
            return
        self.page = 'notes'
        self.layout('Trip notes', self.cancel_notes, form=True)
        self.notes_original = trip['description']
        self.notes_input = self.form_input('description', trip['description'], 'Ideas, reminders, questions...')
        self.notes_input.height = dp(240)
        self.body.add_widget(self.notes_input)
        self.notes_error = text('', color=RED, height=44)
        self.body.add_widget(self.notes_error)
        self.body.add_widget(Action('Save notes', self.save_notes, primary=True))


    def cancel_notes(self):
        if self.notes_input.text != self.notes_original:
            self.confirm('Discard notes?', 'Unsaved note changes will be lost.', 'Discard', lambda: self.show_detail(self.trip_id))
        else:
            self.show_detail(self.trip_id)


    def save_notes(self):
        if len(self.notes_input.text) > 2000:
            self.notes_error.text = 'Use up to 2,000 characters.'
            return
        try:
            with self.store.connect() as db:
                db.execute('UPDATE trips SET description=? WHERE id=? AND pending_delete=0', (self.notes_input.text.strip(), self.trip_id))
        except (sqlite3.Error, OSError):
            self.notes_error.text = 'Could not save notes. Please try again.'
            return
        self.show_detail(self.trip_id)

