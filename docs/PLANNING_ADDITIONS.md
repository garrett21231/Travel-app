# Planning additions

These changes apply the planning discussion from “Set up Travel-app” to the local app in this folder. Calendars, comma costs, photos, custom splits, and the existing look are retained.

## Data and screen changes

| Feature | Where to change it |
| --- | --- |
| Name-only trips, optional budget, ordered stops | `validate_trip()` and `TripStore.save()` in `trip_store.py`; `show_form()` in `trip_ui/trips.py`. Destinations are newline-separated text; `budget_set` distinguishes an unset budget from zero. |
| Default You | UI creation calls `save(..., create_default_traveler=True)`. This only happens for new trips, not migrations or imports. |
| Budget comparison | `show_detail()` in `trip_ui/trips.py` compares `cost_cents` budget to itemized expense totals and separately shows Estimated and Confirmed subtotals. |
| Expense price status | `validate_expense()` and the status spinner in `show_expense_form()` in `trip_ui/expenses.py`. Stored values are `estimated` / `confirmed`, not payment statuses. |
| Connecting flights | `flight_segments` is a JSON list of additional legs. The original flight fields represent the first leg. All details stay inside one expense and contribute no separate price. `add_segment()` / `remove_segment()` manage drafts. |
| Quick notes | `show_notes()` / `save_notes()` in `trip_ui/trips.py` edit the trip's existing `description` field. No second competing notes field is introduced. |
| Duplicate/import/export/summary | `planning_tools.py`. Imports remap IDs, retain photos and named shares, and write the complete validated graph in one transaction. |
| Undo | `stage_delete()` / `finish_delete()` in `planning_tools.py`; `begin_delete()` / `undo_delete()` / `expire_undo()` in `trip_ui/deletion.py`. |

## Undo lifecycle

Deleting in the UI sets `pending_delete=1` and hides the item from active lists and cost totals. It retains the original row and relationships for the ten-second Undo window. A `Clock` event finalizes the deletion using existing foreign-key/cascade rules. Undo clears the flag instead, restoring original identities.

Only one Undo token exists per app session. A new deletion first finalizes any prior token. Normal app shutdown finalizes it as well; startup removes any pending rows left by an interrupted session. Recovery across a closed/reopened app is deliberately unsupported.

For multi-delete, `stage_trip_deletions()` validates all selected active trips before hiding any of them, then sets their flags in one transaction. Its `trip_batch` token contains all selected IDs and counts as one Undo operation. `finish_delete()` restores or permanently removes the entire batch in one transaction; original profiles, photos, expenses, and split associations remain intact throughout the Undo window. The UI also records which list to return to after Undo. Starting another deletion finalizes the previous batch as a whole.

Hiding a traveler preserves their cost responsibility under their saved name and flags affected expenses for review. Undo restores the previous review flags only when the roster and allocations are unchanged; it does not erase review warnings from intervening planning changes. Final profile deletion retains named allocation snapshots, as before.

Storage's existing `delete*()` methods still permanently delete records. The UI uses staged deletion; callers that want Undo must use the staged helpers.

## Portable backups

The JSON envelope contains `format: "trip-planner"`, `version: 1`, and a `trips` list. Each trip bundle includes its record, travelers (photos as base64), expenses, and saved allocations. Import checks names, dates, monetary values, categories, statuses, photo sizes/types, unique IDs, participant relationships, saved counts, and allocation sums before writing any data. Import always adds copies; current trips are never replaced.

Limits: 64 MB encoded file, 100 trips, 999 travelers per trip, 5,000 expenses per trip, 10 MB per photo. Import does not load code or execute SQL from the file. Summaries are separate human-readable text and intentionally omit profile contacts/photos; backups contain them so restoration is complete.

Duplicates use the same validated import path. The copy dialog can clear trip/expense/flight dates and turn Confirmed prices back into Estimated. Existing snapshots for removed travelers remain labeled and flagged for review.

## Migration and verification

Startup adds `budget_set`, `cost_status`, `flight_segments`, and `pending_delete` columns if absent. Existing trip costs remain set budgets, including explicitly stored zero values; old expense prices become Estimated. No automatic import from the other chat or its ZIP occurs.

Run the unit suite and `tests/planning_ui_smoke.py` for these features. The smoke check uses a disposable database and files, verifies the snowboarding example ($850 planned; You $550, Friend $300), notes, optional trip details, duplication options, backup export/import, one-price connecting flights, Undo/expiry, and a narrow display.

`main.py --demo` uses a temporary database containing that example and leaves ordinary saved plans untouched. Desktop validation does not confirm iPhone/Android packaging or device behavior.
