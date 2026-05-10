# Spec: Date Filter for Profile Page

## Overview
Step 6 adds a date-range filter to the profile page so users can slice their
spending data by time period. Currently, all stats, the transaction table, and
the category breakdown reflect the user's full expense history with no way to
narrow the view. After this step, the page will expose four quick-select
presets (This Month, Last 3 Months, Last 6 Months, This Year) plus a custom
date-range picker (from / to inputs). Selecting any filter updates the URL via
a GET form submission, and the route re-queries the database with the chosen
date bounds so that all three data sections (stats, transactions, category
breakdown) reflect only the filtered period.

## Depends on
- Step 1: Database setup (`expenses` table with `date TEXT` column exists)
- Step 2: Registration (users exist)
- Step 3: Login / Logout (`session["user_id"]` is set on login)
- Step 4: Profile page static UI (template structure already in place)
- Step 5: Backend connection (live DB queries already wired into `/profile`)

## Routes
No new routes. The existing `GET /profile` route is extended to read optional
`from` and `to` query-string parameters:

- `GET /profile` — no filter, shows all-time data (existing behaviour)
- `GET /profile?from=YYYY-MM-DD&to=YYYY-MM-DD` — filters all three data
  sections to the given date range — logged-in users only

## Database changes
No new tables or columns. The `expenses.date` column (TEXT, stored as
`YYYY-MM-DD`) is already present and used for ordering. The three existing
helper functions in `database/db.py` are extended with optional `from_date`
and `to_date` parameters; when both are supplied the SQL gains a
`WHERE date BETWEEN ? AND ?` clause (or appended `AND` if the `user_id`
clause already exists).

## Templates
- **Modify**: `templates/profile.html`
  - Add a filter bar between the hero section and the stats cards.
  - The filter bar contains:
    - Four preset `<a>` links: "This Month", "Last 3 Months",
      "Last 6 Months", "This Year" — each builds the correct `?from=&to=`
      URL using Jinja and the `filter_dates` dict passed from the route.
    - A small `<form method="GET" action="{{ url_for('profile') }}">` with
      two `<input type="date">` fields (name=`from`, name=`to`) and a
      "Apply" submit button.
    - An active-state highlight on the preset that matches the current filter.
  - The stat card subtitle changes from the hardcoded "this month" to
    the active filter label passed from the route (e.g. "Last 3 Months" or
    "20 Apr 2026 – 10 May 2026" for custom ranges).
- **No new templates.**

## Files to change
- `database/db.py`
  - `get_recent_expenses(user_id, limit, from_date=None, to_date=None)` —
    add optional date bounds; when both are provided append
    `AND date BETWEEN ? AND ?` to the existing query.
  - `get_expense_stats(user_id, from_date=None, to_date=None)` — same
    pattern; both aggregate queries gain the optional date filter.
  - `get_category_breakdown(user_id, from_date=None, to_date=None)` — same
    pattern.
- `app.py`
  - `profile()` route: read `request.args.get("from")` and
    `request.args.get("to")`, validate that both are valid `YYYY-MM-DD`
    strings (reject/ignore malformed values with `abort(400)`), compute a
    human-readable `filter_label` string, then pass `from_date` / `to_date`
    through to all three DB helpers. Also pass `filter_dates` (dict with
    `from_date`, `to_date`, `active_preset`) to the template.
- `templates/profile.html` — add filter bar as described above.
- `static/css/profile.css` — add styles for the filter bar, preset links,
  active preset state, and date input group; use CSS variables only.

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-strings or string concatenation in SQL
- Date validation in the route must use `datetime.strptime(value, "%Y-%m-%d")`
  inside a `try/except`; invalid dates → `abort(400)`
- If only one of `from` / `to` is supplied, treat the filter as unset and
  show all-time data (do not partially filter)
- Preset date ranges are computed in the route using `datetime` / `date`
  from the standard library — no third-party date helpers
- Use CSS variables — never hardcode hex values in the new CSS
- All templates extend `base.html`
- `url_for()` for every internal link — never hardcode `/profile?...` in
  templates; build the preset URLs with Jinja string interpolation on
  `url_for('profile')` plus the query string
- The filter form must use `method="GET"` — do not POST date filter params
- Currency must always display as ₹ — never £ or $
- Active preset detection: compare the current `from_date` / `to_date`
  against the computed bounds of each preset; mark a preset active only
  when both dates match exactly

## Definition of done
- [ ] Visiting `/profile` with no query params shows all-time data (existing
  behaviour unchanged)
- [ ] Clicking "This Month" updates the URL to `?from=YYYY-MM-01&to=YYYY-MM-DD`
  (first day of the current month to today) and all three sections reflect
  only that period
- [ ] Clicking "Last 3 Months" filters from exactly 3 months before today to
  today; stats and transaction list update accordingly
- [ ] Clicking "Last 6 Months" filters the last 6 calendar months
- [ ] Clicking "This Year" filters from January 1st of the current year to today
- [ ] The active preset is visually highlighted in the filter bar
- [ ] Submitting the custom date form with a valid from/to range filters all
  three sections to that range; no preset is highlighted as active
- [ ] Submitting the custom date form with an invalid date string (e.g.
  "not-a-date") returns a 400 response
- [ ] Supplying only `from` (no `to`) in the URL shows all-time data, not a
  partial filter
- [ ] The stat card subtitle reflects the active filter label (e.g.
  "This Month" or "20 Apr – 10 May 2026"), not the hardcoded "this month"
- [ ] A user with no expenses in the filtered period sees ₹0 total, 0
  transactions, and an empty category list — no errors
