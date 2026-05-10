# Spec: Add Expense

## Overview
Step 7 implements the "Add Expense" feature, giving logged-in users a form to
record a new expense. The stub `GET /expenses/add` route currently returns a
plain string; this step replaces it with a real GET+POST route: GET renders
the form, POST validates and inserts the expense into the database, then
redirects to the profile page. This is the first route that writes to the
`expenses` table, so it also introduces the `create_expense()` DB helper.

## Depends on
- Step 1: Database setup (`expenses` table with all required columns exists)
- Step 2: Registration (users exist in the `users` table)
- Step 3: Login / Logout (`session["user_id"]` is set on login and cleared on logout)
- Step 4: Profile page UI (redirect destination after successful submission)
- Step 5: Backend connection (profile page already reads from `expenses`, so new rows appear immediately)

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate and insert a new expense row, then redirect to `/profile` — logged-in only

## Database changes
No new tables or columns. The `expenses` table already has all required
columns (`user_id`, `title`, `amount`, `category`, `date`, `note`).

One new DB helper is needed:
- `create_expense(user_id, title, amount, category, date, note)` → inserts a
  row and returns the new `id`

## Templates
- **Create:** `templates/add_expense.html`
  - Extends `base.html`
  - A single form with `method="POST"` and `action="{{ url_for('add_expense') }}"`
  - Fields:
    - `title` (text, required) — expense description
    - `amount` (number, step="0.01", min="0.01", required) — amount in ₹
    - `category` (select, required) — one of the 7 valid categories:
      Food, Transport, Shopping, Bills, Entertainment, Health, Other
    - `date` (date, required) — defaults to today's date
    - `note` (textarea, optional) — free-text note
  - Displays an inline error message when validation fails (re-populates
    previously entered values so the user doesn't retype everything)
  - A "Save Expense" submit button
  - A cancel link back to `url_for('profile')`

- **Modify:** `templates/base.html` (if needed)
  - Ensure the nav bar has an "Add Expense" link pointing to
    `url_for('add_expense')` for logged-in users

## Files to change
- `app.py`
  - Replace the stub `add_expense()` route with a full GET+POST handler
  - Import `create_expense` from `database.db`
  - On GET: redirect to login if not authenticated; otherwise render the form
    with today's date pre-filled
  - On POST: validate all required fields, validate amount is a positive
    number, validate category is one of the 7 allowed values, validate date
    is a valid `YYYY-MM-DD` string; on any failure re-render the form with
    the error and the submitted values; on success call `create_expense()`,
    then `redirect(url_for('profile'))`
- `database/db.py`
  - Add `create_expense(user_id, title, amount, category, date, note)` function

## Files to create
- `templates/add_expense.html` — the add-expense form template

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never f-strings or string concatenation in SQL
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- `url_for()` for every internal link — never hardcode paths in templates
- Currency must always display as ₹ — never £ or $
- Unauthenticated requests to both GET and POST must redirect to `/login`
  (check `session.get("user_id")` at the top of the route)
- Amount must be validated as a positive float; reject zero or negative values
- Category must be validated server-side against the exact allowed list —
  do not trust the HTML select value
- Date must be validated with `datetime.strptime(value, "%Y-%m-%d")` inside
  a `try/except`; invalid dates re-render the form with an error
- The note field is optional — store an empty string `""` if omitted
- On validation failure, re-render the form with all previously submitted
  values preserved so the user does not lose their input
- On success, redirect to `url_for('profile')` — do not re-render the form

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in renders a form with title,
  amount, category (dropdown with 7 options), date, and note fields
- [ ] The date field is pre-filled with today's date on page load
- [ ] Submitting the form with all valid fields inserts a row into the
  `expenses` table and redirects to `/profile`
- [ ] The new expense appears in the transaction list on the profile page
  immediately after redirect
- [ ] Submitting with a missing required field (title, amount, category, or
  date) re-renders the form with an error message and all other entered
  values still populated
- [ ] Submitting with amount = 0 or a negative amount re-renders the form
  with a validation error
- [ ] Submitting with a category not in the allowed list returns a 400 or
  re-renders with an error
- [ ] Submitting with an invalid date string re-renders the form with an error
- [ ] The note field is optional — submitting without it succeeds
- [ ] The nav bar shows an "Add Expense" link for logged-in users
