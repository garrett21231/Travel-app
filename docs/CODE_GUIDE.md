# Working on Trip Planner

Start with `main.py` to see how the app is assembled. It contains the single `TripPlannerApp` class, startup state, and launch commands. UI code lives in the `trip_ui/` package, grouped by feature. `trip_store.py` handles validation, calculations, and saved records. The classes and functions include docstrings you can read in the file or through your editor's hover/Go to Definition.

The [planning additions guide](PLANNING_ADDITIONS.md) covers the newer optional-budget flow, multiple stops, connecting flights, backup/duplication, quick notes, and staged Undo. In the current app, trip `cost_cents` is the budget and `budget_set` distinguishes an unset value from $0. The field called `description` is also used by the quick notes editor.

## Project map

| File | Responsibility |
| --- | --- |
| `main.py` | The only Kivy App class, initial shared state, startup, and the optional demo. Run this file. |
| `trip_ui/theme.py` | Shared colors and the absolute bundled asset path. |
| `trip_ui/widgets.py` | Reusable labels, cards, buttons, and outlined containers. |
| `trip_ui/navigation.py` | `NavigationMixin`: page layout, bottom tabs, Back/Escape handling, and shared form inputs. |
| `trip_ui/trips.py` | `TripScreensMixin`: Upcoming/All trips lists, multi-select, trip form, overview/budget, and notes. |
| `trip_ui/expenses.py` | `ExpenseScreensMixin`: expense cards/filters, detail view, category forms, connecting flights, and split controls. |
| `trip_ui/travelers.py` | `TravelerScreensMixin`: traveler progress, cards/forms, cost breakdowns, and photo picker. |
| `trip_ui/dialogs.py` | `DialogsMixin`: Settings, backup import/export, More menu, summary previews, duplication, and confirmations. |
| `trip_ui/deletion.py` | `DeletionMixin`: the shared Undo bar, timer, restoration, finalization, and shutdown cleanup. |
| `trip_store.py` | Validation, money/split calculations, database tables, migrations, and reads/writes. It has no Kivy dependency. |
| `date_picker.py` | `DateField` dropdown calendars, optional flight time inputs, and ISO draft values behind friendly labels. |
| `assets/` | Bundled form outlines and navigation icons exported from Figma. |
| `tests/test_trips.py` | Data validation, persistence, expense details, migration, and profile tests. |
| `tests/test_splits.py` | Everyone/selected/custom shares, exact rounding, trip isolation, and roster changes. |
| `tests/ui_smoke.py` | Temporary-window checks for the main trip/expense/traveler/photo flows. |
| `tests/split_ui_smoke.py` | Temporary-window checks for split controls and traveler breakdowns. |
| `buildozer.spec` | Android packaging configuration; not used when running the Windows development app. |
| `README.md` | Running the app, user-facing behavior, and packaging limitations. |

Running `main.py` does not load `main copy.py`. Changes to that separate copy will not affect the app launched with the README's command. `test_enviornment.py` contains environment checks, rather than the app's feature tests.

## One app, several feature classes

A **mixin** is a class supplying a related group of methods to another class. `TripPlannerApp` inherits the feature mixins and Kivy's `App`. Only `TripPlannerApp` is instantiated and run. The feature classes have no separate app instances or constructors; their `self` is the same running `TripPlannerApp` object.

For example, tapping New trip calls `self.show_form()`, defined in `TripScreensMixin` in `trip_ui/trips.py`. That method calls `self.layout()` from `NavigationMixin` and uses `self.store`, created in `TripPlannerApp.build()`. No copies of navigation state or saved data are passed between screens. Each method has one owner, and feature modules import widgets/data helpers rather than importing `main.py` or each other.

To change a feature, edit its existing method in the corresponding module. You do not need to create another App or add a forwarding method to `main.py`. Adding a new feature mixin requires importing it and listing it among `TripPlannerApp`'s bases; keep method names unique. `Action` remains importable from `main` for compatibility with the existing UI checks, though new UI code should import widgets from `trip_ui.widgets`.

Launch exactly as before: `.\.venv-kivy\Scripts\python.exe main.py`. The `--demo` option, database location, data format, and Android packaging entry point are unchanged.

## How a screen works

The app uses one `TripPlannerApp` object and rebuilds the visible widgets as the user navigates. It does not use a Kivy `ScreenManager`.

1. A button calls a `show_*` method, such as `show_detail(trip_id, 'expenses')`.
2. `layout()` clears the persistent root (`shell`) and creates a new header, scroll view, and vertical content container (`body`).
3. The screen method adds labels, cards, inputs, and actions to `body`.
4. A form's Save action collects strings from inputs, calls `validate_*`, and sends the resulting dictionary to `TripStore.save_*`.
5. A successful save redraws the relevant detail page. Invalid input appears inline and leaves the draft available for correction.

`show_detail()` owns the Overview / Expenses / Travelers tab row. `show_expenses()` and `show_travelers()` append their content to that page. `show_expense_detail()` and `show_traveler_shares()` create separate detail pages with their own Back callbacks.

`navigation(selected)` builds the Upcoming / All trips / Settings bottom tabs. Both navigation bars use `Action(primary=True)` for the selected tab's blue fill and dark text; other tabs stay unfilled. The home page's internal key remains `trips` and its page marker remains `home`. Trip sections also show explicit Trip overview / Expenses / Travelers headings below the tabs. `show_saved()` renders All trips, sorting ISO start dates newest first and inserting one heading per start year; undated trips follow in Dates undecided. `show_settings()` contains the device-wide export/import actions. The trip header's More button opens `show_trip_tools()` for readable summaries and per-trip export, keeping occasional tools out of the overview's editing actions.

On trip detail pages, `show_detail()` moves the title and tab row into a separate container above `scroller`, so tabs stay visible while the body scrolls. The overview's details and budget cards use `content_panel()` and `wrapped_text()` to grow with long values on narrow displays. The same helpers keep trip cards and traveler contact details readable.

`traveler_progress()` compares actual profiles against the planned headcount and offers an Add traveler shortcut when profiles are missing. On the overview it follows the named costs, so the default You profile appears before the invitation to add others, immediately after creating a trip. It does not change existing expense shares. `expense_filters` stores the category and review-only choice for the current trip; switching trips resets it. `show_expenses()` calculates totals from every expense, then filters only the cards. A review-only filter means `split_review` is set; it does not mean the price is estimated. `tests/usability_ui_smoke.py` checks these behaviors, including combined filters, fixed tabs, narrow wrapping, budget states, fresh solo/group trips, and deletion wording.

Trip multi-delete uses `selection_page` and `selected_trip_ids` as temporary UI state. `trip_selection_controls()` pins the count and group actions above the scroller; `trip_card()` adds checkboxes in selection mode and routes card taps to selection instead of navigation. `selectable_trip_ids` limits Select all to the current list, and `prepare_trip_selection()` clears selections when switching lists. `delete_selected_trips()` creates one group Undo token via `stage_trip_deletions()`, then `undo_delete()` restores the entire group and returns to its original list. `tests/bulk_delete_ui_smoke.py` covers the user flow and narrow layout; the planning unit tests verify atomic staging, complete restoration, cascades, invalid selections, and restart cleanup.

| State/attribute | Meaning |
| --- | --- |
| `page` | A navigation marker used by `keyboard()` to route Escape/Back. Forms set it before rendering. |
| `trip_id` | The trip currently being viewed or edited; child forms use it to scope storage operations. |
| `detail_tab` | Which trip tab is currently shown. |
| `shell` | Persistent root layout returned from `build()`. |
| `body`, `scroller` | Current page's content and scroll view, replaced by `layout()`. |
| `inputs`, `expense_inputs`, `traveler_inputs` | Dictionaries of input widgets. Read `.text` to get draft values. |
| `original`, `expense_original`, `traveler_original` | Initial text snapshots used to detect unsaved changes. |
| `split_rows` | Traveler ID → `(row, checkbox, amount input)` for the expense split form. |
| `original_split` | Initial participant checks and amount strings, separate from expense text fields. |
| `traveler_photo`, `original_photo` | Current and initial photo bytes for discard detection. |

These attributes describe the current screen, not durable records. Navigate away and the widgets are replaced. Saving to `TripStore` makes changes durable.

## Kivy conventions used here

- `bind(on_release=...)` connects a button event to an action. `Action` wraps that event so its callback takes no arguments.
- `bind(text=...)`, `bind(active=...)`, and `bind(size=...)` react to widget property changes. Callback parameters like `*_` accept unused event arguments.
- `dp()` scales layout dimensions with device density; `sp()` scales text sizes.
- `size_hint_y=None` makes a widget use its explicit height. The scrolling body's height follows `minimum_height`, allowing long forms to scroll.
- `canvas.before` draws card/button backgrounds. Their position and size bindings keep drawings aligned with widgets.
- A fixed-height `Panel` must fit child heights, gaps, and top/bottom padding. Increase its height when adding a row.
- For longer labels, set `shorten=False`. Notes also bind height to `texture_size` so wrapped text remains readable.
- `DateField.text` contains ISO strings (`2020-01-12`, or `2020-01-12 08:30` for flights), while its button shows a friendly date. It supports the same `.text`/`bind(text=...)` interface used by form code. `display_date()` formats stored dates on detail pages and cards. Keep formatting at the display boundary so date sorting/validation stays correct.
- `parse_cost()` is the shared dollar-to-cent parser for trip estimates, expenses, and custom allocations. It accepts correctly grouped thousands commas without changing integer-cent storage.
- In loops, callbacks use `lambda tid=traveler_id: ...` to capture the current ID. Without the default argument, every button could act on the final loop item.

## Data and money rules

Form validators accept strings and raise `ValueError` with a message suitable for the UI. They return dictionaries containing normalized values: integer `people`, integer or absent `age`, and integer money amounts in cents. `validate_expense()` checks expense fields; `calculate_split()` checks participants and individual amounts.

| Value | Meaning |
| --- | --- |
| Trip `cost_cents` | The original trip estimate, separate from actual expense totals. |
| Expense `cost_cents` | The entered group total or per-person rate, depending on `cost_basis`. |
| `cost_basis` | `group` or `per_person`. |
| `split_mode` | `everyone`, `selected`, or `custom`. |
| `split_count` | Participant count saved when the expense was last explicitly saved. |
| `split_review` | Whether roster changes or unassigned shares need user review. |
| Share `amount_cents` | One traveler's recorded responsibility for one expense. |

For example, a per-person expense with `cost_cents=20000` and `split_count=4` has a group total of $800.00. `expense_total_cents()` calculates one expense's total; `TripStore.expense_total()` sums expenses in SQL using the same rule. If you change pricing rules, keep both implementations consistent.

`money()` formats or averages amounts for display. It does not create saved allocations. `calculate_split()` allocates whole cents and distributes the remainder in sorted traveler ID order: $10.00 split three ways becomes $3.34 + $3.33 + $3.33. Custom dollar strings must sum exactly to the expense total.

Saving an expense snapshots its participants and replaces its allocations. Adding/removing profiles or editing the trip headcount does not silently recalculate those saved amounts. Everyone without profiles uses the planned headcount and produces no named allocations; it is marked for review.

## Database and upgrades

The real database is `trips.sqlite3` under Kivy's `App.user_data_dir`. Tests pass a separate `database_path`, so they do not modify real trips.

| Table | Relationship/lifecycle |
| --- | --- |
| `trips` | Parent record for a plan. |
| `expenses` | Belongs to one trip; deleted with that trip. |
| `travelers` | Belongs to one trip; includes the optional photo as a BLOB. |
| `expense_shares` | Belongs to an expense; stores a profile reference, name snapshot, and cents. |

`TripStore.connect()` enables foreign keys, starts a transaction context, commits on success, rolls back on an exception, and always closes the connection. `save_expense()` writes the expense and all shares in that same transaction, preventing half-saved splits.

Deleting an expense cascades to its shares. Deleting a traveler sets its share reference to `NULL`, while retaining the saved name and amount; affected expenses get a review flag. Deleting a trip removes its child expenses, profiles/photos, and shares.

Schema upgrades live in `TripStore.__init__()`: it inspects `PRAGMA table_info` and adds missing columns with compatible defaults. The first split upgrade snapshots old headcounts and flags expenses for review. Reopening an already-upgraded database should not overwrite existing data.

## Where to make common changes

| Desired change | Start here |
| --- | --- |
| Colors | Palette constants in `trip_ui/theme.py`. |
| Shared buttons and card spacing | `Action`, `Panel`, and `OutlineRow` in `trip_ui/widgets.py`. |
| Shared form inputs | `form_input()` in `trip_ui/navigation.py`; expense dropdowns use `expense_spinner()` in `trip_ui/expenses.py`. |
| Page padding/title/header | `layout()` in `trip_ui/navigation.py`. |
| Calendar appearance/navigation | `DateField` in `date_picker.py`; `form_input()` decides which fields use it. |
| Visible date format | `display_date()` and `MONTH_NAMES` in `trip_store.py`; storage remains ISO. |
| Accepted cost formats | `parse_cost()` in `trip_store.py`, shared by all cost validation. |
| Expense card details | `show_expenses()` in `trip_ui/expenses.py`; card height follows content so wrapped participant/provider labels fit. |
| Trip fields or hints | `show_form()` in `trip_ui/trips.py`; update `validate_trip()`, SQL schema, and `TripStore.fields` for new saved fields. |
| Expense categories | `EXPENSE_CATEGORIES`; also check category-specific validation and UI sections. |
| Flight/lodging field visibility | `show_expense_form()` and `refresh_expense_specific()` in `trip_ui/expenses.py`. |
| Saved expense details | `validate_expense()`, `EXPENSE_DETAILS`, schema defaults, `show_expense_detail()`, and form inputs. |
| Pricing or split rules | `calculate_split()`, `expense_total_cents()`, and `TripStore.expense_total()`. |
| Split form controls or preview | `refresh_expense_split()`, `split_form_values()`, and `update_expense_preview()` in `trip_ui/expenses.py`. |
| Traveler fields | `show_traveler_form()` in `trip_ui/travelers.py`; `validate_traveler()` and the traveler table/save field list in `trip_store.py`. |
| Traveler cost breakdown | `show_traveler_shares()` and `TripStore.traveler_shares()`. |
| Photo formats or size | `MAX_PHOTO_BYTES`, `photo_format()`, `choose_traveler_photo()`, and `select_traveler_photo()`. |
| Back navigation/new pages | Set `page`, supply the header Back callback, and extend `keyboard()` as needed. |
| Settings, backups, summary, duplication | `trip_ui/dialogs.py`; validation/serialization stays in `planning_tools.py`. |
| Deletion/Undo timer and bar | `trip_ui/deletion.py`; transaction helpers stay in `planning_tools.py`. |
| Confirmation text | Calls to `confirm()` in each feature; its shared layout is in `trip_ui/dialogs.py`. |

### Adding a saved expense field

For a simple optional text field such as a booking reference:

1. Add its key to `EXPENSE_DETAILS`, and align the values tuple and argument list in `validate_expense()` with that order.
2. Add the input/label to `show_expense_form()` and the display label to `show_expense_detail()`.
3. If it appears only for one category, include it in `refresh_expense_specific()` and clear it for other categories in validation.
4. The existing migration loop adds fields in `EXPENSE_DETAILS` as text columns with blank defaults; `expense_fields` includes them for writes. Fields with another type need an explicit migration and matching normalization.
5. Add a round-trip persistence test and a test upgrading an old database. Check that editing an expense preserves the new value.

Changing only a visible label is simpler than renaming a saved key. For instance, the existing `arrival_at` TODO would require a deliberate data migration if the key changes; changing its caption alone retains storage compatibility, but should still accurately describe what that date means.

### Adding a category

Append the category to `EXPENSE_CATEGORIES`. The dropdown and category subtotals read that tuple. If the category needs extra fields, update the form's specific-widget list, visibility method, validation, migration defaults, and detail page as described above. Renaming a category already stored in records also requires migrating those saved values.

## Checking a change

Run from the project folder:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q main.py trip_ui trip_store.py planning_tools.py date_picker.py
```

For changes to screens or interactions, also run the relevant temporary-window check:

```powershell
.\.venv-kivy\Scripts\python.exe tests\ui_smoke.py
.\.venv-kivy\Scripts\python.exe tests\split_ui_smoke.py
.\.venv-kivy\Scripts\python.exe tests\calendar_ui_smoke.py
.\.venv-kivy\Scripts\python.exe tests\planning_ui_smoke.py
.\.venv-kivy\Scripts\python.exe tests\navigation_ui_smoke.py
.\.venv-kivy\Scripts\python.exe tests\usability_ui_smoke.py
.\.venv-kivy\Scripts\python.exe tests\bulk_delete_ui_smoke.py
```

UI checks create temporary databases and save screenshots under `tests/artifacts/`. Inspect the screenshots as well as the test result: a button callback can work while its label or card layout still needs adjustment. They are desktop development checks; physical-device packaging, touch, keyboard, and native gallery behavior remain separate verification work.
