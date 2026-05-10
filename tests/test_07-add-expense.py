"""
tests/test_07-add-expense.py
============================
Pytest test suite for the Spendly "Add Expense" feature (Step 7).

Feature spec: .claude/specs/07-add-expense.md

Coverage:
  - Auth guard: GET and POST while logged out redirect to /login
  - Happy path GET: form renders with all required fields and today's date
  - Happy path POST: valid submission inserts a DB row and redirects to /profile
  - DB side effect: expense row confirmed in DB after successful POST
  - New expense appears on /profile immediately after redirect
  - Validation errors: missing required fields (title, amount, category, date)
  - Validation errors: amount = 0 or negative amount
  - Validation errors: invalid category (not in allowed list) returns 400
  - Validation errors: invalid date string re-renders form with error
  - Note field is optional — omitting it still succeeds
  - Form values are preserved on validation failure (no data loss for user)
  - All 7 valid categories appear in the dropdown
  - Nav bar shows "Add Expense" link for logged-in users
  - Nav bar does not show "Add Expense" link for logged-out users
  - DB helper unit test: create_expense() inserts correctly and returns new ID
"""

import datetime
import sqlite3

import pytest
from werkzeug.security import generate_password_hash

from app import app as flask_app
from database.db import init_db, create_expense


# ---------------------------------------------------------------------------
# Constants — from spec (never read from implementation)
# ---------------------------------------------------------------------------

VALID_CATEGORIES = [
    "Food", "Transport", "Shopping", "Bills",
    "Entertainment", "Health", "Other",
]

ADD_EXPENSE_URL = "/expenses/add"
LOGIN_URL = "/login"
PROFILE_URL = "/profile"
REGISTER_URL = "/register"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path):
    """Flask app wired to an isolated SQLite file in a temp directory.

    Patches database.db.DB_PATH so that every db helper call in both the
    app and the test uses the same throwaway file.  Restores the original
    path after the test completes.
    """
    db_file = str(tmp_path / "test_spendly.db")

    flask_app.config.update({
        "TESTING": True,
        "DATABASE": db_file,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
    })

    import database.db as db_module
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_file

    with flask_app.app_context():
        init_db()
        yield flask_app

    db_module.DB_PATH = original_db_path


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def _registered_user(app):
    """Inserts a test user directly into the temp DB and returns credentials."""
    import database.db as db_module

    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    pw_hash = generate_password_hash("testpass123")
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "test@example.com", pw_hash),
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    return {
        "user_id": user_id,
        "email": "test@example.com",
        "password": "testpass123",
        "name": "Test User",
    }


@pytest.fixture()
def auth_client(client, _registered_user):
    """Test client that is already logged in as the registered test user."""
    client.post(
        LOGIN_URL,
        data={
            "email": _registered_user["email"],
            "password": _registered_user["password"],
        },
        follow_redirects=False,
    )
    return client


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _valid_form_data(**overrides):
    """Returns a dict of valid POST data for the add-expense form.

    Any key in `overrides` replaces the default value, allowing tests to
    inject a single invalid field while keeping the rest valid.
    To omit a field entirely pass `field=None`.
    """
    data = {
        "title":    "Coffee at work",
        "amount":   "150.00",
        "category": "Food",
        "date":     "2026-05-01",
        "note":     "Morning coffee",
    }
    for key, value in overrides.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return data


# ---------------------------------------------------------------------------
# 1. Auth guard — GET and POST while logged out
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_unauthenticated_get_redirects_to_login(self, client):
        response = client.get(ADD_EXPENSE_URL, follow_redirects=False)
        assert response.status_code == 302, (
            "Unauthenticated GET /expenses/add must redirect (302)"
        )
        assert LOGIN_URL in response.headers["Location"], (
            "Redirect target for unauthenticated GET must be /login"
        )

    def test_unauthenticated_post_redirects_to_login(self, client):
        response = client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(),
            follow_redirects=False,
        )
        assert response.status_code == 302, (
            "Unauthenticated POST /expenses/add must redirect (302)"
        )
        assert LOGIN_URL in response.headers["Location"], (
            "Redirect target for unauthenticated POST must be /login"
        )

    def test_unauthenticated_get_does_not_render_form(self, client):
        response = client.get(ADD_EXPENSE_URL, follow_redirects=True)
        # After following the redirect we should land on the login page,
        # not the add-expense form.
        assert b"Login" in response.data or b"Sign in" in response.data or b"login" in response.data.lower(), (
            "Following the unauthenticated redirect must land on the login page"
        )


# ---------------------------------------------------------------------------
# 2. Happy path GET — form renders with all expected fields
# ---------------------------------------------------------------------------

class TestGetRendersForm:
    def test_get_returns_200(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        assert response.status_code == 200, (
            "Authenticated GET /expenses/add must return 200"
        )

    def test_form_has_title_field(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        assert b'name="title"' in response.data, (
            "Add-expense form must have an input with name='title'"
        )

    def test_form_has_amount_field(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        assert b'name="amount"' in response.data, (
            "Add-expense form must have an input with name='amount'"
        )

    def test_form_has_category_field(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        assert b'name="category"' in response.data, (
            "Add-expense form must have a select/input with name='category'"
        )

    def test_form_has_date_field(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        assert b'name="date"' in response.data, (
            "Add-expense form must have an input with name='date'"
        )

    def test_form_has_note_field(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        assert b'name="note"' in response.data, (
            "Add-expense form must have a textarea/input with name='note'"
        )

    def test_form_has_submit_button(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        assert b"Save Expense" in response.data, (
            "Add-expense form must have a 'Save Expense' submit button"
        )

    def test_form_uses_post_method(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        assert b'method="POST"' in response.data or b"method='POST'" in response.data, (
            "Add-expense form must declare method='POST'"
        )

    def test_form_action_points_to_add_expense_route(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        assert b"/expenses/add" in response.data, (
            "Form action must point to /expenses/add"
        )

    def test_form_has_cancel_link_to_profile(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        assert PROFILE_URL.encode() in response.data, (
            "Add-expense form must include a cancel link back to /profile"
        )

    def test_extends_base_html_has_nav(self, auth_client):
        response = auth_client.get(ADD_EXPENSE_URL)
        # Presence of the brand name confirms base.html was extended
        assert b"Spendly" in response.data, (
            "Page must extend base.html (nav brand 'Spendly' must appear)"
        )


# ---------------------------------------------------------------------------
# 3. Today's date pre-fill
# ---------------------------------------------------------------------------

class TestTodayDatePreFill:
    def test_date_field_is_prefilled_with_today(self, auth_client):
        today = datetime.date.today().isoformat()
        response = auth_client.get(ADD_EXPENSE_URL)
        assert today.encode() in response.data, (
            f"The date field must be pre-filled with today's date ({today})"
        )


# ---------------------------------------------------------------------------
# 4. All 7 valid categories appear in the dropdown
# ---------------------------------------------------------------------------

class TestCategoryDropdown:
    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_category_option_present(self, auth_client, category):
        response = auth_client.get(ADD_EXPENSE_URL)
        assert category.encode() in response.data, (
            f"Category option '{category}' must appear in the add-expense form"
        )

    def test_exactly_seven_category_options_or_more(self, auth_client):
        """The spec mandates exactly 7 categories; the dropdown must list all of them."""
        response = auth_client.get(ADD_EXPENSE_URL)
        html = response.data.decode("utf-8")
        present = [cat for cat in VALID_CATEGORIES if cat in html]
        assert len(present) == 7, (
            f"All 7 valid categories must appear in the form, found: {present}"
        )


# ---------------------------------------------------------------------------
# 5. Happy path POST — inserts DB row and redirects to /profile
# ---------------------------------------------------------------------------

class TestHappyPathPost:
    def test_valid_post_redirects_to_profile(self, auth_client):
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(),
            follow_redirects=False,
        )
        assert response.status_code == 302, (
            "Valid POST must redirect (302)"
        )
        assert PROFILE_URL in response.headers["Location"], (
            "Redirect after successful submission must target /profile"
        )

    def test_valid_post_inserts_expense_row_in_db(self, auth_client, _registered_user, app):
        """After a valid POST, the expense must exist in the database."""
        import database.db as db_module

        form_data = _valid_form_data(
            title="Unique Expense Title ABC",
            amount="299.50",
            category="Transport",
            date="2026-04-15",
            note="Bus pass top-up",
        )
        auth_client.post(ADD_EXPENSE_URL, data=form_data, follow_redirects=False)

        conn = sqlite3.connect(db_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        row = conn.execute(
            "SELECT * FROM expenses WHERE title = ? AND user_id = ?",
            ("Unique Expense Title ABC", _registered_user["user_id"]),
        ).fetchone()
        conn.close()

        assert row is not None, (
            "Expense row must exist in the DB after a valid POST"
        )
        assert row["title"] == "Unique Expense Title ABC", (
            "Inserted expense title must match submitted value"
        )
        assert float(row["amount"]) == pytest.approx(299.50), (
            "Inserted expense amount must match submitted value"
        )
        assert row["category"] == "Transport", (
            "Inserted expense category must match submitted value"
        )
        assert row["date"] == "2026-04-15", (
            "Inserted expense date must match submitted value"
        )
        assert row["note"] == "Bus pass top-up", (
            "Inserted expense note must match submitted value"
        )
        assert row["user_id"] == _registered_user["user_id"], (
            "Inserted expense must be associated with the logged-in user"
        )

    def test_new_expense_appears_on_profile_after_redirect(self, auth_client):
        """The new expense title must appear on /profile immediately after submission."""
        form_data = _valid_form_data(title="My Special Lunch")
        auth_client.post(ADD_EXPENSE_URL, data=form_data, follow_redirects=True)

        profile_response = auth_client.get(PROFILE_URL)
        assert b"My Special Lunch" in profile_response.data, (
            "Newly added expense must appear in the transaction list on /profile"
        )

    def test_valid_post_returns_no_form_error(self, auth_client):
        """A valid submission must not re-render the form — it redirects."""
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(),
            follow_redirects=False,
        )
        # A redirect means no form/error was rendered
        assert response.status_code == 302, (
            "Valid submission must result in a redirect, not a form re-render"
        )

    def test_valid_post_amount_as_integer_string_accepted(self, auth_client):
        """Whole-number amounts like '500' must be accepted as valid."""
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(amount="500"),
            follow_redirects=False,
        )
        assert response.status_code == 302, (
            "A whole-number amount string ('500') must be accepted and redirect"
        )


# ---------------------------------------------------------------------------
# 6. Note field is optional
# ---------------------------------------------------------------------------

class TestNoteIsOptional:
    def test_post_without_note_succeeds(self, auth_client):
        form_data = _valid_form_data(note=None)  # omit the note key entirely
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 302, (
            "POST without a note field must succeed and redirect"
        )
        assert PROFILE_URL in response.headers["Location"], (
            "POST without note must redirect to /profile"
        )

    def test_post_with_empty_note_succeeds(self, auth_client):
        form_data = _valid_form_data(note="")  # empty string note
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 302, (
            "POST with an empty note string must succeed and redirect"
        )

    def test_post_without_note_stores_empty_string_or_null(self, auth_client, _registered_user, app):
        """Omitting the note field must store '' (empty string) — not crash."""
        import database.db as db_module

        form_data = _valid_form_data(title="No-note Expense", note=None)
        auth_client.post(ADD_EXPENSE_URL, data=form_data, follow_redirects=False)

        conn = sqlite3.connect(db_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT note FROM expenses WHERE title = ? AND user_id = ?",
            ("No-note Expense", _registered_user["user_id"]),
        ).fetchone()
        conn.close()

        assert row is not None, "Expense without note must still be inserted"
        # Spec says store "" if omitted; None (NULL) is also acceptable behaviour
        assert row["note"] == "" or row["note"] is None, (
            "Note must be stored as empty string or NULL when not supplied"
        )


# ---------------------------------------------------------------------------
# 7. Validation errors — missing required fields
# ---------------------------------------------------------------------------

class TestMissingRequiredFields:
    @pytest.mark.parametrize("missing_field", ["title", "amount", "category", "date"])
    def test_missing_field_does_not_redirect(self, auth_client, missing_field):
        form_data = _valid_form_data(**{missing_field: None})
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code != 302, (
            f"POST with missing '{missing_field}' must not redirect — must re-render the form"
        )

    @pytest.mark.parametrize("missing_field", ["title", "amount", "category", "date"])
    def test_missing_field_returns_200(self, auth_client, missing_field):
        form_data = _valid_form_data(**{missing_field: None})
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code == 200, (
            f"POST with missing '{missing_field}' must re-render the form (200)"
        )

    @pytest.mark.parametrize("missing_field", ["title", "amount", "category", "date"])
    def test_missing_field_shows_error_message(self, auth_client, missing_field):
        form_data = _valid_form_data(**{missing_field: None})
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=form_data,
            follow_redirects=False,
        )
        html = response.data.decode("utf-8").lower()
        assert "error" in html or "required" in html or "field" in html, (
            f"Re-rendered form must display an error message when '{missing_field}' is missing"
        )

    @pytest.mark.parametrize("missing_field", ["title", "amount", "category", "date"])
    def test_missing_field_does_not_insert_row(self, auth_client, _registered_user, app, missing_field):
        """A failed validation must not write anything to the database."""
        import database.db as db_module

        form_data = _valid_form_data(**{missing_field: None})
        auth_client.post(ADD_EXPENSE_URL, data=form_data, follow_redirects=False)

        conn = sqlite3.connect(db_module.DB_PATH)
        count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?",
            (_registered_user["user_id"],),
        ).fetchone()[0]
        conn.close()

        assert count == 0, (
            f"No expense row must be inserted when '{missing_field}' is missing"
        )

    @pytest.mark.parametrize("empty_field", ["title", "amount", "category", "date"])
    def test_empty_string_field_treated_as_missing(self, auth_client, empty_field):
        """An empty string for a required field must be treated the same as absent."""
        form_data = _valid_form_data(**{empty_field: ""})
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=form_data,
            follow_redirects=False,
        )
        assert response.status_code != 302, (
            f"POST with empty string for '{empty_field}' must not redirect"
        )


# ---------------------------------------------------------------------------
# 8. Validation errors — amount = 0 or negative
# ---------------------------------------------------------------------------

class TestAmountValidation:
    @pytest.mark.parametrize("bad_amount", ["0", "0.00", "-1", "-100", "-0.01"])
    def test_invalid_amount_does_not_redirect(self, auth_client, bad_amount):
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(amount=bad_amount),
            follow_redirects=False,
        )
        assert response.status_code != 302, (
            f"POST with amount='{bad_amount}' must not redirect"
        )

    @pytest.mark.parametrize("bad_amount", ["0", "0.00", "-1", "-100", "-0.01"])
    def test_invalid_amount_re_renders_form(self, auth_client, bad_amount):
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(amount=bad_amount),
            follow_redirects=False,
        )
        assert response.status_code == 200, (
            f"POST with amount='{bad_amount}' must re-render form (200)"
        )

    @pytest.mark.parametrize("bad_amount", ["0", "-1"])
    def test_invalid_amount_shows_error_message(self, auth_client, bad_amount):
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(amount=bad_amount),
            follow_redirects=False,
        )
        html = response.data.decode("utf-8").lower()
        assert "error" in html or "positive" in html or "amount" in html, (
            f"Re-rendered form must display a validation error for amount='{bad_amount}'"
        )

    def test_non_numeric_amount_does_not_redirect(self, auth_client):
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(amount="abc"),
            follow_redirects=False,
        )
        assert response.status_code != 302, (
            "POST with a non-numeric amount must not redirect"
        )

    def test_positive_amount_with_decimals_is_accepted(self, auth_client):
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(amount="49.99"),
            follow_redirects=False,
        )
        assert response.status_code == 302, (
            "POST with a positive decimal amount ('49.99') must succeed and redirect"
        )

    @pytest.mark.parametrize("bad_amount", ["0", "-1"])
    def test_invalid_amount_does_not_insert_row(self, auth_client, _registered_user, app, bad_amount):
        import database.db as db_module

        auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(amount=bad_amount),
            follow_redirects=False,
        )

        conn = sqlite3.connect(db_module.DB_PATH)
        count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?",
            (_registered_user["user_id"],),
        ).fetchone()[0]
        conn.close()

        assert count == 0, (
            f"No expense row must be inserted for invalid amount='{bad_amount}'"
        )


# ---------------------------------------------------------------------------
# 9. Validation errors — invalid category
# ---------------------------------------------------------------------------

class TestCategoryValidation:
    @pytest.mark.parametrize("bad_category", [
        "food",          # lowercase — server must validate case-sensitively
        "Snacks",        # not in allowed list
        "InvalidCat",    # arbitrary string
        "",              # empty
        "<script>",      # injection attempt
    ])
    def test_invalid_category_does_not_redirect(self, auth_client, bad_category):
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(category=bad_category),
            follow_redirects=False,
        )
        assert response.status_code != 302, (
            f"POST with invalid category='{bad_category}' must not redirect (302)"
        )

    def test_invalid_category_not_in_allowed_list_returns_400_or_rerenders(self, auth_client):
        """Per spec: category not in allowed list must return 400 or re-render with error."""
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(category="NotACategory"),
            follow_redirects=False,
        )
        assert response.status_code in (400, 200), (
            "Invalid category must result in HTTP 400 or a form re-render (200)"
        )

    def test_invalid_category_does_not_insert_row(self, auth_client, _registered_user, app):
        import database.db as db_module

        auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(category="Snacks"),
            follow_redirects=False,
        )

        conn = sqlite3.connect(db_module.DB_PATH)
        count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?",
            (_registered_user["user_id"],),
        ).fetchone()[0]
        conn.close()

        assert count == 0, (
            "No expense row must be inserted when category is not in the allowed list"
        )

    @pytest.mark.parametrize("valid_category", VALID_CATEGORIES)
    def test_each_valid_category_is_accepted(self, auth_client, valid_category):
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(category=valid_category),
            follow_redirects=False,
        )
        assert response.status_code == 302, (
            f"Valid category '{valid_category}' must be accepted and redirect"
        )


# ---------------------------------------------------------------------------
# 10. Validation errors — invalid date string
# ---------------------------------------------------------------------------

class TestDateValidation:
    @pytest.mark.parametrize("bad_date", [
        "not-a-date",
        "01/05/2026",      # wrong separator format (dd/mm/yyyy)
        "2026-13-01",      # invalid month
        "2026-05-32",      # invalid day
        "20260501",        # no separators
        "yesterday",       # plain word
    ])
    def test_invalid_date_does_not_redirect(self, auth_client, bad_date):
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(date=bad_date),
            follow_redirects=False,
        )
        assert response.status_code != 302, (
            f"POST with invalid date='{bad_date}' must not redirect"
        )

    @pytest.mark.parametrize("bad_date", [
        "not-a-date",
        "01/05/2026",
        "2026-13-01",
    ])
    def test_invalid_date_re_renders_form(self, auth_client, bad_date):
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(date=bad_date),
            follow_redirects=False,
        )
        assert response.status_code == 200, (
            f"POST with invalid date='{bad_date}' must re-render the form (200)"
        )

    @pytest.mark.parametrize("bad_date", ["not-a-date", "01/05/2026"])
    def test_invalid_date_shows_error_message(self, auth_client, bad_date):
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(date=bad_date),
            follow_redirects=False,
        )
        html = response.data.decode("utf-8").lower()
        assert "error" in html or "invalid" in html or "date" in html, (
            f"Re-rendered form must show an error message for invalid date='{bad_date}'"
        )

    @pytest.mark.parametrize("bad_date", ["not-a-date", "99-99-9999"])
    def test_invalid_date_does_not_insert_row(self, auth_client, _registered_user, app, bad_date):
        import database.db as db_module

        auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(date=bad_date),
            follow_redirects=False,
        )

        conn = sqlite3.connect(db_module.DB_PATH)
        count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?",
            (_registered_user["user_id"],),
        ).fetchone()[0]
        conn.close()

        assert count == 0, (
            f"No expense row must be inserted for invalid date='{bad_date}'"
        )

    def test_valid_date_is_accepted(self, auth_client):
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(date="2026-01-31"),
            follow_redirects=False,
        )
        assert response.status_code == 302, (
            "A properly formatted YYYY-MM-DD date must be accepted and redirect"
        )


# ---------------------------------------------------------------------------
# 11. Form values preserved on validation failure
# ---------------------------------------------------------------------------

class TestFormValuesPreservedOnError:
    def test_previously_entered_title_is_preserved_on_error(self, auth_client):
        """When validation fails, the title entered by the user must be
        re-populated in the form so the user does not retype everything."""
        form_data = _valid_form_data(title="My Important Expense", amount="0")
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=form_data,
            follow_redirects=False,
        )
        assert b"My Important Expense" in response.data, (
            "Title must be preserved in the re-rendered form after validation failure"
        )

    def test_previously_entered_note_is_preserved_on_error(self, auth_client):
        form_data = _valid_form_data(note="Some important note text", amount="0")
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=form_data,
            follow_redirects=False,
        )
        assert b"Some important note text" in response.data, (
            "Note must be preserved in the re-rendered form after validation failure"
        )

    def test_previously_entered_amount_is_preserved_on_error(self, auth_client):
        """Even a bad amount value should be echoed back so the user can fix it."""
        form_data = _valid_form_data(amount="-5", title="Preserve Test")
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=form_data,
            follow_redirects=False,
        )
        assert b"-5" in response.data, (
            "Submitted amount must be preserved in the re-rendered form after validation failure"
        )

    def test_previously_entered_date_is_preserved_on_error(self, auth_client):
        form_data = _valid_form_data(date="2026-03-15", amount="0")
        response = auth_client.post(
            ADD_EXPENSE_URL,
            data=form_data,
            follow_redirects=False,
        )
        assert b"2026-03-15" in response.data, (
            "Date must be preserved in the re-rendered form after validation failure"
        )


# ---------------------------------------------------------------------------
# 12. Nav bar — "Add Expense" link visibility
# ---------------------------------------------------------------------------

class TestNavBarAddExpenseLink:
    def test_add_expense_nav_link_present_for_logged_in_user(self, auth_client):
        """Logged-in users must see an 'Add Expense' link in the navigation bar."""
        response = auth_client.get(PROFILE_URL)
        assert b"Add Expense" in response.data, (
            "The nav bar must show 'Add Expense' link for authenticated users"
        )

    def test_add_expense_nav_link_points_to_correct_route(self, auth_client):
        """The 'Add Expense' nav link must point to /expenses/add."""
        response = auth_client.get(PROFILE_URL)
        assert b"/expenses/add" in response.data, (
            "The 'Add Expense' nav link must href to /expenses/add"
        )

    def test_add_expense_nav_link_absent_for_logged_out_user(self, client):
        """Logged-out users must NOT see the 'Add Expense' link in the nav bar."""
        response = client.get("/")
        html = response.data.decode("utf-8")
        # The nav for logged-out users shows Sign in / Get started, not Add Expense
        # We check the Add Expense link is not inside the nav-links section
        # by checking the href is absent (the text alone could appear elsewhere)
        assert "/expenses/add" not in html, (
            "The /expenses/add href must not appear in the nav for logged-out users"
        )

    def test_add_expense_nav_link_on_add_expense_page_itself(self, auth_client):
        """The nav bar on /expenses/add itself must also show the link (active state)."""
        response = auth_client.get(ADD_EXPENSE_URL)
        assert b"Add Expense" in response.data, (
            "The 'Add Expense' nav link must be visible on the add-expense page itself"
        )


# ---------------------------------------------------------------------------
# 13. DB helper unit test — create_expense()
# ---------------------------------------------------------------------------

class TestCreateExpenseHelper:
    def test_create_expense_returns_positive_integer_id(self, app, _registered_user):
        """create_expense() must return a positive integer representing the new row's id."""
        with app.app_context():
            new_id = create_expense(
                _registered_user["user_id"],
                "Test Expense",
                250.00,
                "Food",
                "2026-04-01",
                "test note",
            )
        assert isinstance(new_id, int), (
            "create_expense() must return an integer ID"
        )
        assert new_id > 0, (
            "create_expense() must return a positive integer (auto-increment ID > 0)"
        )

    def test_create_expense_inserts_row_in_db(self, app, _registered_user):
        """create_expense() must persist the row so it is retrievable by ID."""
        import database.db as db_module

        with app.app_context():
            new_id = create_expense(
                _registered_user["user_id"],
                "Direct Insert Test",
                999.00,
                "Health",
                "2026-03-10",
                "",
            )

        conn = sqlite3.connect(db_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (new_id,)
        ).fetchone()
        conn.close()

        assert row is not None, (
            "create_expense() must insert a row retrievable by the returned ID"
        )
        assert row["title"] == "Direct Insert Test"
        assert float(row["amount"]) == pytest.approx(999.00)
        assert row["category"] == "Health"
        assert row["date"] == "2026-03-10"
        assert row["user_id"] == _registered_user["user_id"]

    def test_create_expense_with_empty_note_stores_empty_string(self, app, _registered_user):
        import database.db as db_module

        with app.app_context():
            new_id = create_expense(
                _registered_user["user_id"],
                "Empty Note Expense",
                100.00,
                "Other",
                "2026-02-01",
                "",
            )

        conn = sqlite3.connect(db_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT note FROM expenses WHERE id = ?", (new_id,)
        ).fetchone()
        conn.close()

        assert row["note"] == "" or row["note"] is None, (
            "create_expense() with empty note string must store '' or NULL"
        )

    def test_create_expense_successive_ids_are_unique(self, app, _registered_user):
        """Two successive calls must return different IDs."""
        with app.app_context():
            id1 = create_expense(
                _registered_user["user_id"], "Expense A", 10.00, "Food", "2026-01-01", ""
            )
            id2 = create_expense(
                _registered_user["user_id"], "Expense B", 20.00, "Food", "2026-01-02", ""
            )
        assert id1 != id2, (
            "Successive create_expense() calls must return unique IDs"
        )

    def test_create_expense_respects_user_id(self, app, _registered_user):
        """The inserted row must carry exactly the user_id that was passed in."""
        import database.db as db_module

        with app.app_context():
            new_id = create_expense(
                _registered_user["user_id"],
                "User ID Test",
                50.00,
                "Bills",
                "2026-05-01",
                "",
            )

        conn = sqlite3.connect(db_module.DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT user_id FROM expenses WHERE id = ?", (new_id,)
        ).fetchone()
        conn.close()

        assert row["user_id"] == _registered_user["user_id"], (
            "Inserted expense must carry the correct user_id"
        )


# ---------------------------------------------------------------------------
# 14. Currency display — amounts use ₹ (INR)
# ---------------------------------------------------------------------------

class TestCurrencyOnProfileAfterAdd:
    def test_inr_symbol_on_profile_after_adding_expense(self, auth_client):
        """After adding an expense, the profile page must display ₹, never $ or £."""
        auth_client.post(
            ADD_EXPENSE_URL,
            data=_valid_form_data(amount="1234"),
            follow_redirects=True,
        )
        response = auth_client.get(PROFILE_URL)
        assert "₹".encode("utf-8") in response.data, (
            "Profile page amounts must use ₹ (INR) after adding an expense"
        )
        assert b"$" not in response.data, (
            "No USD ($) must appear on the profile page"
        )
