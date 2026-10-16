"""Expense cards, filters, details, forms, flight legs, and split controls."""
import sqlite3
import json
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from trip_store import validate_expense, money, EXPENSE_CATEGORIES, expense_total_cents, calculate_split, display_date
from trip_ui.theme import BLACK, WHITE, BLUE, MUTED, RED, ASSETS
from trip_ui.widgets import text, wrapped_text, Panel, Action


class ExpenseScreensMixin:
    """Expense cards, filters, details, forms, flight legs, and split controls.

    Mixed into TripPlannerApp; self is the one running app, not a separate
    screen instance. Shared state is documented in docs/CODE_GUIDE.md.
    """

    # Read-only list, filters, and full expense details.
    def show_expenses(self, trip, expenses, total):
        """Append totals, category breakdowns, review flags, and expense cards.

        The trip average is informational; actual responsibility is recorded
        in each expense's named shares and may be uneven.
        """
        self.body.add_widget(text('Total planned', size=14, color=MUTED, height=24))
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
        category, review_only = self.expense_filters
        if expenses:
            self.body.add_widget(text('Filter expenses', size=16, bold=True))
            self.expense_filter_category = self.expense_spinner(category, ('All categories',) + EXPENSE_CATEGORIES)
            self.expense_filter_category.bind(text=lambda _, value: self.show_detail(trip['id'], 'expenses', category_filter=value))
            self.body.add_widget(self.expense_filter_category)
            row = BoxLayout(size_hint_y=None, height=dp(40))
            self.expense_filter_review = CheckBox(active=review_only, size_hint_x=None, width=dp(44))
            self.expense_filter_review.bind(active=lambda _, value: self.show_detail(trip['id'], 'expenses', review_only=value))
            row.add_widget(self.expense_filter_review)
            row.add_widget(Action('Needs split review only', lambda: self.show_detail(trip['id'], 'expenses', review_only=not review_only),
                                  font_size=sp(13), color=WHITE))
            self.body.add_widget(row)
        visible = [expense for expense in expenses
                   if (category == 'All categories' or expense['category'] == category)
                   and (not review_only or expense['split_review'])]
        if expenses:
            self.body.add_widget(text(f'Showing {len(visible)} of {len(expenses)} expenses', size=13, color=MUTED))
        if category != 'All categories' or review_only:
            self.body.add_widget(Action('Clear filters', lambda: self.show_detail(trip['id'], 'expenses', category_filter='All categories', review_only=False)))
            if expenses and not visible:
                self.body.add_widget(wrapped_text('No expenses match these filters. Clear filters to see everything.', color=MUTED))
        if not expenses:
            panel = Panel(104)
            panel.add_widget(text("You don't have any expenses for this trip.\nAdd a flight, hotel, or anything else above.",
                                  color=BLACK, height=76, bold=True))
            self.body.add_widget(panel)
        # Totals and category breakdowns above always include the whole trip;
        # filters affect cards only, never the saved costs or responsibilities.
        for expense in visible:
            panel = Panel(0)
            panel.bind(minimum_height=panel.setter('height'))
            panel.add_widget(wrapped_text(expense['name'], size=16, color=BLACK, bold=True))
            panel.add_widget(text(expense['category'], color=BLACK, size=13, height=20))
            panel.add_widget(text('Price: ' + expense['cost_status'].capitalize(), color=BLACK, size=13, height=20))
            panel.add_widget(text(money(expense_total_cents(expense, trip['people'])) + ' USD total', color=BLACK, height=24))
            shares = self.store.expense_shares(trip['id'], expense['id'])
            participants = ', '.join(share['name'] + (' (removed)' if share['traveler_id'] is None else '') for share in shares)
            if not participants:
                participants = f"{expense['split_count']} planned travelers; not assigned yet"
            rows = [('Shared by', participants), ('Date', display_date(expense['expense_date'])),
                    ('Place/provider', expense['provider'] or 'Not set')]
            if expense['cost_basis'] == 'per_person':
                rows.insert(0, ('Price per person', money(expense['cost_cents']) + ' USD'))
            for caption, value in rows:
                detail = text(f'{caption}: {value}', color=BLACK, size=13, height=24)
                detail.shorten = False
                detail.bind(width=lambda w, _: setattr(w, 'text_size', (w.width, None)),
                            texture_size=lambda w, size: setattr(w, 'height', max(dp(24), size[1])))
                panel.add_widget(detail)
            if expense['split_review']:
                panel.add_widget(text('Split needs review', color=(.65, .1, .1, 1), size=13, height=20))
            actions = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
            expense_id = expense['id']
            panel.add_widget(Action('View details', lambda eid=expense_id: self.show_expense_detail(eid)))
            actions.add_widget(Action('Edit expense', lambda eid=expense_id: self.show_expense_form(eid)))
            actions.add_widget(Action('Delete', lambda eid=expense_id: self.confirm('Delete expense?',
                                      'Removes this expense from the trip.\nUndo is available for 10 seconds.', 'Delete',
                                      lambda: self.delete_expense(eid)), color=RED))
            panel.add_widget(actions)
            self.body.add_widget(panel)


    def show_expense_detail(self, expense_id):
        """Show full expense fields and allocations, including removed travelers."""
        expense = self.store.get_expense(self.trip_id, expense_id)
        if not expense:
            self.show_detail(self.trip_id, 'expenses')
            return
        self.page = 'expense_detail'
        self.layout(expense['name'], lambda: self.show_detail(self.trip_id, 'expenses'))
        trip = self.store.get(self.trip_id)
        self.body.add_widget(text(expense['category'], color=BLUE))
        self.body.add_widget(text(expense['cost_status'].capitalize() + ' price / not a payment status', color=MUTED, size=13))
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
                formatted = display_date(expense[key]) if key in ('expense_date', 'departure_at', 'arrival_at', 'check_in', 'check_out') else expense[key]
                value = text(formatted, size=16, height=28)
                value.shorten = False
                value.bind(width=lambda w, _: setattr(w, 'text_size', (w.width, None)),
                           texture_size=lambda w, size: setattr(w, 'height', max(dp(28), size[1])))
                self.body.add_widget(value)
        for index, segment in enumerate(json.loads(expense['flight_segments']), 2):
            self.body.add_widget(text(f'Flight {index} (same booking)', size=18, bold=True, height=32))
            for key, caption in labels.items():
                if segment.get(key):
                    value = display_date(segment[key]) if key in ('departure_at', 'arrival_at') else segment[key]
                    self.body.add_widget(text(f'{caption}: {value}', size=14, height=32))
        self.body.add_widget(text('Notes', size=20, height=38, bold=True))
        notes = text(expense['description'] or 'No notes added.', size=15, height=40)
        notes.shorten = False
        notes.bind(width=lambda w, _: setattr(w, 'text_size', (w.width, None)),
                   texture_size=lambda w, value: setattr(w, 'height', max(dp(40), value[1])))
        self.body.add_widget(notes)
        self.body.add_widget(Action('Edit expense', lambda: self.show_expense_form(expense_id), primary=True))


    # Editable expense drafts; saving delegates validation to trip_store.py.
    def expense_spinner(self, value, choices):
        """Create a dropdown with the same outline and typography as form inputs."""
        return Spinner(text=value, values=choices, size_hint_y=None, height=dp(49),
                       font_size=sp(16), color=WHITE, background_color=WHITE,
                       background_normal=str(ASSETS / 'field.png'), background_down=str(ASSETS / 'field.png'),
                       border=(15, 15, 15, 15))


    def show_expense_form(self, expense_id=None):
        """Build expense fields, split controls, category-specific fields, and preview.

        All specific inputs exist in expense_inputs even when hidden, preserving
        drafts during category switches. Validation clears unrelated fields on
        save. split_rows maps profile IDs to (row, checkbox, amount input).
        """
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
        self.body.add_widget(text('Price status (does not indicate payment)', size=14, height=20))
        self.expense_status = self.expense_spinner(expense['cost_status'].capitalize() if expense else 'Estimated', ('Estimated', 'Confirmed'))
        self.body.add_widget(self.expense_status)
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
        # Keep the same widgets when switching categories, so draft text survives.
        for key, caption, hint in specific:
            self.expense_inputs[key] = self.form_input(key, expense[key] if expense else '', hint)
            self.expense_specific_widgets[key] = text(caption + ' (optional)', size=14, height=20)
        self.expense_specific = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(12))
        self.expense_specific.bind(minimum_height=self.expense_specific.setter('height'))
        self.segment_rows = []
        for segment in json.loads(expense['flight_segments']) if expense else []:
            self.add_segment(segment, redraw=False)
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
        # Expense fields and participant amounts are separate snapshots because
        # they are validated/saved through different arguments in the data layer.
        self.original_split = self.split_form_values()
        self.expense_error = text('', color=RED, size=14, height=60)
        self.body.add_widget(self.expense_error)
        self.body.add_widget(Action('Save expense', self.save_expense_form, primary=True))


    def refresh_expense_specific(self, *_):
        """Attach only the current category's extra fields, retaining their drafts."""
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
        if category == 'Flights':
            for index, widgets in enumerate(self.segment_rows, 2):
                self.expense_specific.add_widget(text(f'Flight {index} / no additional booking cost', size=16, height=30, bold=True))
                for key, caption in [('airline', 'Airline'), ('flight_number', 'Flight number'), ('departure_airport', 'Departure airport'),
                                      ('arrival_airport', 'Arrival airport'), ('departure_at', 'Departure date & time'), ('arrival_at', 'Arrival date & time')]:
                    self.expense_specific.add_widget(text(caption, size=14, height=20))
                    self.expense_specific.add_widget(widgets[key])
                self.expense_specific.add_widget(Action('Remove this connection', lambda row=widgets: self.remove_segment(row)))
            self.expense_specific.add_widget(Action('+ Add connecting flight', self.add_segment))


    def add_segment(self, segment=None, redraw=True):
        """Each extra leg adds details to one booking; only the expense has a price."""
        if len(self.segment_rows) >= 12:
            return
        values = segment or {}
        self.segment_rows.append({key: self.form_input(key, values.get(key, ''), 'Optional') for key in
                                  ('airline', 'flight_number', 'departure_airport', 'arrival_airport', 'departure_at', 'arrival_at')})
        if redraw:
            self.refresh_expense_specific()


    def remove_segment(self, row):
        self.segment_rows.remove(row)
        self.refresh_expense_specific()


    def expense_form_values(self):
        """Collect strings and translate visible dropdown labels to saved values."""
        return dict(**{key: field.text for key, field in self.expense_inputs.items()},
                    cost_status=self.expense_status.text.lower(),
                    flight_segments=[{key: field.text for key, field in row.items()} for row in self.segment_rows],
                    category=self.expense_category.text, cost_basis='per_person' if self.expense_basis.text == 'Per person' else 'group',
                    split_mode={'Everyone': 'everyone', 'Selected travelers': 'selected', 'Custom amounts': 'custom'}[self.expense_split_mode.text])


    def split_form_values(self):
        """Return checked profile IDs and their dollar strings; unchecked rows vanish."""
        ids = [tid for tid, (_, check, _) in self.split_rows.items() if check.active]
        amounts = {tid: amount.text for tid, (_, check, amount) in self.split_rows.items() if check.active}
        return ids, amounts


    # Participant choices and exact-cost previews; no saved shares change here.
    def refresh_expense_split(self, *_):
        """Toggle participant checks/custom inputs and update explanatory text.

        Everyone checks all profiles. Custom mode shows amount inputs; other
        modes remove those inputs from the layout without deleting their drafts.
        """
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
        """Use the real split rules for a draft preview, with no database writes."""
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
        """Confirm changed fields or participant amounts before discarding the draft."""
        def go_back():
            self.show_detail(self.trip_id, 'expenses')
        if self.expense_form_values() != self.expense_original or self.split_form_values() != self.original_split:
            self.confirm('Discard changes?', 'Your unsaved expense changes will be lost.', 'Discard', go_back)
        else:
            go_back()


    def save_expense_form(self):
        """Validate fields and save expense/shares atomically; display failure inline."""
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
        """Delete an expense after confirmation and redraw the trip's expense tab."""
        try:
            self.begin_delete('expenses', expense_id)
        except (sqlite3.Error, OSError):
            self.confirm("Couldn't delete expense", 'Please try again.', 'OK', lambda: None)
            return
        self.show_detail(self.trip_id, 'expenses')

