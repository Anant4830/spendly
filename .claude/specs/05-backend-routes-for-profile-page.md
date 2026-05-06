# Spec: Profile Page Backend

## Overview
This feature replaces the hardcoded dummy data in the `/profile` route with real data queried from the SQLite database. The profile page already has a complete UI (built in Step 4); this step wires it up to the `users` and `expenses` tables so that each logged-in user sees their own name, email, member-since date, transaction history, summary stats, and category breakdown. No new routes or templates are needed — only new DB helper functions and an updated route handler.

## Depends on
- Step 1: Database setup (`users` and `expenses` tables must exist)
- Step 2: Registration (user accounts must be creatable)
- Step 3: Login + Logout (`session["user_id"]` must be set after login)
- Step 4: Profile Page Design (`profile.html` template must exist)

## Routes
No new routes. The existing `GET /profile` route is updated to pass real data instead of hardcoded dicts.

## Database changes
No new tables or columns. All data comes from the existing `users` and `expenses` tables.

## Templates
- **Modify:** `templates/profile.html` — update date display format if needed to match data returned from DB (date stored as `YYYY-MM-DD` text, displayed as `DD Mon YYYY`)

## Files to change
- `app.py` — update `/profile` route: replace hardcoded dicts with calls to new DB helpers; format amounts as ₹ strings; compute initials from user name
- `database/db.py` — add four new helper functions (see below)

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()`
- Parameterised queries only — never f-strings in SQL
- Passwords hashed with werkzeug (no changes to auth in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Close every DB connection after use
- Amounts stored as `REAL` — format as `₹X,XXX` strings in the route, not in the template
- Dates stored as `YYYY-MM-DD` — format as `DD Mon YYYY` in the route

## New DB helpers to add in `database/db.py`

### `get_user_by_id(user_id)`
```
SELECT id, name, email, created_at FROM users WHERE id = ?
```
Returns a single Row or None.

### `get_recent_expenses(user_id, limit=10)`
```
SELECT id, title, amount, category, date
FROM expenses
WHERE user_id = ?
ORDER BY date DESC, id DESC
LIMIT ?
```
Returns a list of Rows.

### `get_expense_stats(user_id)`
```
SELECT
    COALESCE(SUM(amount), 0) AS total_spent,
    COUNT(*) AS transaction_count
FROM expenses
WHERE user_id = ?
```
Top category computed with a second query:
```
SELECT category, SUM(amount) AS cat_total
FROM expenses
WHERE user_id = ?
GROUP BY category
ORDER BY cat_total DESC
LIMIT 1
```
Returns a dict with keys: `total_spent`, `transaction_count`, `top_category` (string, or `"—"` if no expenses).

### `get_category_breakdown(user_id)`
```
SELECT category, SUM(amount) AS total
FROM expenses
WHERE user_id = ?
GROUP BY category
ORDER BY total DESC
```
Returns a list of dicts with `name`, `amount` (formatted ₹ string), `pct` (integer percentage of overall total).

## Definition of done
- [ ] Logged-in user sees their own name and email on the profile page (not "Demo User")
- [ ] Member-since date reflects the user's actual `created_at` from the DB
- [ ] Transaction history shows the user's real expenses, newest first
- [ ] Stats row shows the correct total spent, transaction count, and top category
- [ ] Category breakdown reflects real expense data with correct percentages
- [ ] A brand-new registered user with no expenses sees ₹0, 0 transactions, and empty category rows (no crash)
- [ ] The demo user (seeded via `seed_db`) sees the 7 sample expenses from the seed
- [ ] Visiting `/profile` while logged out still redirects to `/login`
