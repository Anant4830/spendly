# Spec: Registration

## Overview
Implement user registration so a visitor can create a Spendly account with their
name, email, and password. This is the first step in the auth flow: it introduces
form handling, server-side validation, password hashing, and session creation.
After a successful registration the user is logged in automatically and redirected
to `/login` (the dashboard is not yet built; this will be updated in a later step).

---

## Depends on
- Step 01 — Database Setup (`get_db()`, `init_db()`, `users` table must exist)

---

## Routes
- `GET /register` — render registration form — public (already exists, keep as-is)
- `POST /register` — validate form data, insert user, start session, redirect — public

---

## Database changes
No new tables or columns. The `users` table from Step 01 is sufficient.

Two new helper functions are needed in `database/db.py`:

- `create_user(name, email, password_hash)` — inserts a new row into `users`, returns the new `id`
- `get_user_by_email(email)` — fetches a single `users` row by email, returns `None` if not found

---

## Templates

**Modify:** `templates/register.html`
- Fix hardcoded `action="/register"` → `action="{{ url_for('register') }}"`
- Add `value="{{ name or '' }}"` and `value="{{ email or '' }}"` to inputs so
  values are preserved when the form is re-rendered on error
- Template already handles `{% if error %}` — no structural changes needed

---

## Files to change
- `app.py` — add POST /register route; add `request`, `redirect`, `url_for`, `session`
  to Flask imports; set `app.secret_key`
- `database/db.py` — add `create_user()` and `get_user_by_email()`
- `templates/register.html` — fix hardcoded action URL; add sticky field values

---

## Files to create
None

---

## New dependencies
No new dependencies. `werkzeug.security.generate_password_hash` is already
available via the existing `werkzeug` install.

---

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` only
- Parameterised queries only — never use f-strings or `%` formatting in SQL
- Hash passwords with `werkzeug.security.generate_password_hash` before storing
- Use CSS variables — never hardcode hex values in any new or modified CSS
- All templates must extend `base.html`
- `app.secret_key` must be set before any session usage; use a hard-coded dev
  string for now (e.g. `"spendly-dev-secret"`) — a real secret from env is a
  later hardening step
- DB logic must stay in `database/db.py` — the route in `app.py` may only call
  helper functions, not write SQL directly
- Use `abort(400)` for malformed requests; re-render the form with an `error`
  string for user-facing validation failures

### POST /register validation rules (in order)
1. All three fields (`name`, `email`, `password`) must be non-empty — error:
   `"All fields are required."`
2. Password must be at least 8 characters — error: `"Password must be at least 8 characters."`
3. Email must not already exist in `users` — error: `"An account with that email already exists."`
4. If all checks pass: hash password, call `create_user()`, set `session['user_id']`,
   redirect to `url_for('login')`

---

## Definition of done
- [ ] `GET /register` still renders the form without errors
- [ ] Submitting the form with all fields empty re-renders the form with
      `"All fields are required."` and preserves entered values
- [ ] Submitting with a password shorter than 8 characters shows the password
      length error and preserves name and email
- [ ] Submitting a duplicate email shows `"An account with that email already exists."`
- [ ] Submitting valid data creates a new row in `users` with a hashed password
      (not plaintext) and redirects to `/login`
- [ ] After a successful registration `session['user_id']` is set to the new
      user's id
- [ ] The form action uses `url_for('register')`, not a hardcoded string
- [ ] All DB operations use parameterised queries
