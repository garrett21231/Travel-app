# Trip Planner

A small native Kivy app based on the supplied Figma Trip Planner screens: black backgrounds, white cards, and blue accents. No accounts, APIs, maps, or network requests. All trips are saved in a local SQLite database under Kivy's app data directory.

## Run on Windows

From this folder in PowerShell:

```powershell
.\.venv-kivy\Scripts\python.exe main.py
```

For a fresh Python environment, install `requirements.txt` first. The existing environment already has Kivy.

To explore an isolated snowboarding example without changing saved trips:

```powershell
.\.venv-kivy\Scripts\python.exe main.py --demo
```

## Use

- Use **+ New trip** above the trip list to create a trip with just a name. Destinations, dates, budget, and notes can remain undecided. New trips include an editable traveler called **You**; planned headcount defaults to one. **Select** sits at the top right for deleting multiple trips.
- Enter ordered destinations one per line. Calendar dropdowns display dates like **Jan 12, 2027**. Flight time inputs use local 24-hour `HH:MM` time.
- The **Trip budget** is independent of **Planned cost so far**, which sums itemized expenses once each. An unset budget differs from a deliberately entered $0 budget. The overview shows the difference, Estimated/Confirmed subtotals, and each traveler's share. An incomplete expense list is not a final trip quote.
- Add expenses in Flights, Lodging, Food & drink, Transportation, Activities, or Other. Use **Estimated** for provisional amounts and **Confirmed** for known prices; neither status tracks payments.
- Group-total or per-person costs can apply to Everyone, Selected travelers, or Custom amounts. Exact cents and saved participant counts keep shares stable until explicitly reviewed. Comma-grouped amounts such as `1,250.00` work in budgets, costs, and custom shares.
- Flight expenses can contain a first flight plus optional connecting flights. All legs belong to a single priced booking; adding a connection never adds another charge. Lodging includes optional check-in/check-out dates.
- Traveler profiles support optional age, phone, email, gender, and a locally selected PNG/JPEG photo. Photos are stored in SQLite. Profile removal preserves named expense shares for review rather than silently redistributing costs.
- Open All trips to revisit every trip, grouped by start year and ordered newest first within each year. Cross-year trips use their start year; trips without dates appear last under Dates undecided and also remain under Upcoming on the home screen.
- Trip tabs stay visible as you scroll. The compact overview groups Budget, Planned, and Remaining (or Over budget), with a separate count of named travelers versus the planned headcount. Long titles, destinations, and traveler contacts wrap on smaller screens.
- Bottom navigation is Upcoming / All trips / Settings. The current tab has a blue filled background in both navigation bars; trip sections also have clear Trip overview, Expenses, or Travelers headings.
- To delete several trips, tap **Select** on Upcoming or All trips, tap the trips or their checkboxes, then **Delete (count)** and confirm. **Select all** covers only the current list (Upcoming excludes past trips). **Cancel**, Back, or changing tabs clears selection. One **Undo** restores the entire deleted group, including its expenses and travelers, for 10 seconds.
- Expenses can be filtered by category and by Needs split review, together or separately. Clear filters restores all cards; totals always cover the entire trip.
- Use **Edit notes** for a lightweight trip note without reopening the full form.
- **Duplicate trip** copies profiles/photos, expenses, and allocations independently. The dialog lets you clear dates and reset Confirmed prices to Estimated.
- The trip screen's **More** menu contains **Readable summary** and **Export this trip**. Readable summary previews text you can copy or save. It includes costs and names but excludes profile contact details and photos. Delivery through another app is a manual action.
- **Export this trip**, or **Export backup** in the Settings tab, produces a versioned JSON backup, including profile contacts/photos. **Import backup** in Settings validates the whole file and adds independent copies; it never overwrites existing trips. Files up to 64 MB / 100 trips are supported.
- Confirmed deletions offer **Undo for 10 seconds**. Only the latest deletion is recoverable; a new deletion finalizes the previous one. Closing/reopening the app finalizes pending deletions. Undo restores original record identities and associations. This is not a permanent trash folder.

The existing black, white, and blue look and Figma assets are retained. Everything works locally without an account or network service. Currency is currently USD. Native phone gallery/share-sheet integration is not implemented; local file selection and copy/save actions are available.

See [the code guide](docs/CODE_GUIDE.md) and [planning additions](docs/PLANNING_ADDITIONS.md) for implementation details. Existing databases upgrade automatically without resetting saved plans; old trip estimates become budgets and existing expenses start as Estimated.

The app still runs through the single `TripPlannerApp` class in `main.py`. UI feature classes now live in `trip_ui/`: `trips.py`, `expenses.py`, `travelers.py`, `navigation.py`, `dialogs.py`, and `deletion.py`. Reusable widgets and colors are in `widgets.py` and `theme.py`. The code guide explains how those classes share the one app instance and where to edit each feature.

## Verification

```powershell
python -m unittest discover -s tests -v
.\.venv-kivy\Scripts\python.exe tests\ui_smoke.py
.\.venv-kivy\Scripts\python.exe tests\split_ui_smoke.py
.\.venv-kivy\Scripts\python.exe tests\calendar_ui_smoke.py
.\.venv-kivy\Scripts\python.exe tests\planning_ui_smoke.py
.\.venv-kivy\Scripts\python.exe tests\navigation_ui_smoke.py
.\.venv-kivy\Scripts\python.exe tests\usability_ui_smoke.py
.\.venv-kivy\Scripts\python.exe tests\bulk_delete_ui_smoke.py
```

The UI smoke check opens a temporary phone-sized window, exercises create/edit/delete and validation, checks persistence by reopening storage, and writes screenshots to `tests/artifacts/`. It uses a temporary database, so it does not modify real saved trips.

## Mobile packaging

This is mobile-oriented Kivy source and a runnable desktop development version; it is not an installed Android/iOS binary. `buildozer.spec` is provided for Android packaging on Linux/WSL with Buildozer and the Android build tools installed. Run `buildozer android debug` there. iOS packaging requires macOS, Xcode, and kivy-ios. Device builds and touch/keyboard behavior still need testing on a physical device.
