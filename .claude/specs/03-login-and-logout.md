# Spec: Login and Logout

## Overview
Implement credential-based login and session-based logout for Spendly. A visitor
submits their email and password; the server verifies them against the hashed value
in the database, starts a session, and redirects to `/profile`. Logout clears the
session and redirects to the landing page. This step completes the core auth loop
started in Step 02 and gates all future logged-in pages behind `session['user_id']`.

---

## Depends on
- Step 01 — Database Setup (`get_db()`, `users` table, `get_user_by_email()` must exist)
- Step 02 — Registration (`app.secret_key` set, `session` imported, `get_user_by_email()` added)

---

## Routes
- `GET /login` — render login form; redirect to `/profile` if already logged in — public
- `POST /login` — validate credentials, set session, redirect to `/profile` — public
- `GET /logout` — clear session, redirect to `/` — any (logged-in or not)

---

## Database changes
No new tables or columns.

No new helper functions needed — `get_user_by_email(email)` added in Step 02 is
sufficient. Password verification happens in `app.py` using
`werkzeug.security.check_password_hash`, which is not DB logic.

---

## Templates

**Modify:** `templates/login.html`
- Wrap inputs in a `<form method="POST" action="{{ url_for('login') }}">` element
- Add `name="email"` and `name="password"` attributes to the relevant inputs
- Preserve submitted email on re-render: `value="{{ email or '' }}"`
- Display `{{ error }}` when present (an `{% if error %}` block)

**Modify:** `templates/base.html`
- In the navigation, show **Logout** link when `session.get('user_id')` is truthy
- Show **Login** and **Register** links when there is no active session
- Use `url_for()` for all nav links — never hardcode paths

---

## Files to change
- `app.py` — add `check_password_hash` to werkzeug import; implement `POST /login`
  with validation and session; implement `GET /logout` to clear session and redirect;
  update `GET /login` to redirect logged-in users
- `templates/login.html` — add POST form, sticky email field, error display
- `templates/base.html` — conditional nav links based on `session.get('user_id')`

---

## Files to create
None

---

## New dependencies
No new dependencies. `werkzeug.security.check_password_hash` is already available
via the existing `werkzeug` install (used by `generate_password_hash` in Step 02).

---

## Rules for implementation
- No SQLAlchemy or ORMs — use raw `sqlite3` via `get_db()` only
- Parameterised queries only — never f-strings or `%` formatting in SQL
- Verify passwords with `werkzeug.security.check_password_hash` — never compare plaintext
- Use CSS variables — never hardcode hex values in any new or modified CSS
- All templates must extend `base.html`
- DB logic stays in `database/db.py` — routes may only call helper functions
- Use `redirect(url_for(...))` after a successful login (Post/Redirect/Get pattern)
- Use `session.clear()` in logout — do not pop keys individually
- Do not show which field (email vs password) is wrong — use a single generic error
  `"Invalid email or password."` to avoid user enumeration

### POST /login validation rules (in order)
1. Both fields (`email`, `password`) must be non-empty — error: `"All fields are required."`
2. Look up user by email with `get_user_by_email(email)` — if not found, error:
   `"Invalid email or password."`
3. Check hash with `check_password_hash(user['password_hash'], password)` — if
   mismatch, same error: `"Invalid email or password."`
4. If all checks pass: set `session['user_id'] = user['id']` and
   `session['user_name'] = user['name']`, then redirect to `url_for('profile')`

---

## Definition of done
- [ ] `GET /login` renders the form for unauthenticated users
- [ ] `GET /login` redirects to `/profile` when `session['user_id']` is already set
- [ ] Submitting an empty form re-renders with `"All fields are required."` and
      preserves the entered email
- [ ] Submitting an unknown email shows `"Invalid email or password."`
- [ ] Submitting a known email with the wrong password shows `"Invalid email or password."`
- [ ] Submitting correct credentials sets `session['user_id']` and `session['user_name']`
      and redirects to `/profile`
- [ ] `GET /logout` clears the session completely and redirects to `/`
- [ ] After logout, `session['user_id']` is no longer present
- [ ] The nav shows Login and Register links when logged out
- [ ] The nav shows a Logout link when logged in
- [ ] The form action uses `url_for('login')`, not a hardcoded string
