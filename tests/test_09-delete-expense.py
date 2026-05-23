"""
tests/test_09-delete-expense.py
================================
Pytest test suite for the Spendly "Delete Expense" feature (Step 9).

Feature spec: .claude/specs/09-delete-expense.md

Coverage:
  - DB helper unit test: delete_expense() removes the row for matching user_id
  - DB helper unit test: delete_expense() leaves the row for wrong user_id (no error)
  - DB helper unit test: delete_expense() with non-existent id raises no error
  - Route auth guard: unauthenticated POST redirects to /login (302)
  - Route auth guard: unauthenticated POST does not touch DB
  - Route happy path: authenticated POST on own expense redirects to /profile (302)
  - Route happy path: row is gone from DB after successful delete
  - Route happy path: deleted title absent from /profile after redirect
  - Route happy path: sibling expenses are unaffected
  - Route ownership guard: authenticated POST for another user's expense returns 404
  - Route ownership guard: the other user's row is still in DB after the attempted delete
  - Route 404: authenticated POST for non-existent id returns 404
  - HTTP semantics: GET to the delete URL returns 405 Method Not Allowed
  - UI: profile page shows a Delete button/form per expense row with correct action URL
"""

import sqlite3

import pytest
from werkzeug.security import generate_password_hash

from app import app as flask_app
from database.db import init_db, delete_expense, create_expense

import database.db as db_module


# ---------------------------------------------------------------------------
# URL constants
# ---------------------------------------------------------------------------

LOGIN_URL   = "/login"
PROFILE_URL = "/profile"


# ---------------------------------------------------------------------------
# Fixtures — mirror the established pattern from test_07-add-expense.py
# ---------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path):
    """Flask app wired to an isolated SQLite file in a per-test temp directory.

    Patches database.db.DB_PATH so that every db helper and every route handler
    that calls get_db() all hit the same throwaway file.  The original path is
    restored after the test completes.
    """
    db_file = str(tmp_path / "test_spendly.db")

    flask_app.config.update({
        "TESTING": True,
        "DATABASE": db_file,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
    })

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
    """Inserts a primary test user directly into the temp DB and returns credentials."""
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
        "user_id":  user_id,
        "email":    "test@example.com",
        "password": "testpass123",
        "name":     "Test User",
    }


@pytest.fixture()
def _second_user(app):
    """Inserts a second test user to verify cross-user ownership guards."""
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    pw_hash = generate_password_hash("otherpass456")
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Other User", "other@example.com", pw_hash),
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    return {
        "user_id":  user_id,
        "email":    "other@example.com",
        "password": "otherpass456",
        "name":     "Other User",
    }


@pytest.fixture()
def auth_client(client, _registered_user):
    """Test client already logged in as the primary test user."""
    client.post(
        LOGIN_URL,
        data={
            "email":    _registered_user["email"],
            "password": _registered_user["password"],
        },
        follow_redirects=False,
    )
    return client


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _insert_expense(
    user_id,
    title="Chai",
    amount=30.0,
    category="Food",
    date="2026-05-01",
    note="",
):
    """Directly inserts an expense row and returns its auto-increment id."""
    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    cursor = conn.execute(
        "INSERT INTO expenses (user_id, title, amount, category, date, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, title, amount, category, date, note),
    )
    conn.commit()
    expense_id = cursor.lastrowid
    conn.close()
    return expense_id


def _expense_exists(expense_id):
    """Returns True if an expense row with the given id is present in the DB."""
    conn = sqlite3.connect(db_module.DB_PATH)
    row = conn.execute(
        "SELECT id FROM expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    conn.close()
    return row is not None


# ---------------------------------------------------------------------------
# 1. DB helper unit tests — delete_expense()
# ---------------------------------------------------------------------------

class TestDeleteExpenseHelper:

    def test_delete_removes_row_for_correct_user(self, app, _registered_user):
        """delete_expense(id, correct_user_id) must remove the row from the DB."""
        expense_id = _insert_expense(_registered_user["user_id"], title="Expense to delete")

        assert _expense_exists(expense_id), (
            "Precondition: expense must exist before calling delete_expense"
        )

        with app.app_context():
            delete_expense(expense_id, _registered_user["user_id"])

        assert not _expense_exists(expense_id), (
            "delete_expense() with the correct user_id must remove the row from the DB"
        )

    def test_delete_leaves_row_for_wrong_user(self, app, _registered_user, _second_user):
        """delete_expense(id, wrong_user_id) must leave the row untouched."""
        expense_id = _insert_expense(_registered_user["user_id"], title="Should survive")

        with app.app_context():
            delete_expense(expense_id, _second_user["user_id"])  # wrong owner

        assert _expense_exists(expense_id), (
            "delete_expense() with a wrong user_id must not remove the row"
        )

    def test_delete_wrong_user_does_not_raise(self, app, _registered_user, _second_user):
        """delete_expense with a wrong user_id must not raise any exception."""
        expense_id = _insert_expense(_registered_user["user_id"])

        try:
            with app.app_context():
                delete_expense(expense_id, _second_user["user_id"])
        except Exception as exc:
            pytest.fail(
                f"delete_expense() with a wrong user_id raised an unexpected exception: {exc}"
            )

    def test_delete_nonexistent_id_does_not_raise(self, app, _registered_user):
        """delete_expense with a non-existent expense_id must not raise any exception."""
        nonexistent_id = 999999

        try:
            with app.app_context():
                delete_expense(nonexistent_id, _registered_user["user_id"])
        except Exception as exc:
            pytest.fail(
                f"delete_expense() with a non-existent id raised an unexpected exception: {exc}"
            )

    def test_delete_nonexistent_id_leaves_db_unchanged(self, app, _registered_user):
        """delete_expense on a non-existent id must not affect existing rows."""
        expense_id = _insert_expense(_registered_user["user_id"], title="Untouched row")
        nonexistent_id = expense_id + 10000  # guaranteed absent

        with app.app_context():
            delete_expense(nonexistent_id, _registered_user["user_id"])

        assert _expense_exists(expense_id), (
            "delete_expense() with a non-existent id must leave other rows intact"
        )

    def test_delete_only_removes_specified_row(self, app, _registered_user):
        """Deleting one expense must not affect a sibling expense of the same user."""
        id_to_delete = _insert_expense(
            _registered_user["user_id"], title="Delete me", amount=100.0
        )
        id_to_keep = _insert_expense(
            _registered_user["user_id"], title="Keep me", amount=200.0
        )

        with app.app_context():
            delete_expense(id_to_delete, _registered_user["user_id"])

        assert not _expense_exists(id_to_delete), (
            "Targeted expense must be removed"
        )
        assert _expense_exists(id_to_keep), (
            "Sibling expense must remain untouched after deleting a different row"
        )


# ---------------------------------------------------------------------------
# 2. Route — auth guard (unauthenticated)
# ---------------------------------------------------------------------------

class TestDeleteRouteAuthGuard:

    def test_unauthenticated_post_redirects_to_login(self, client, app, _registered_user):
        """POST /expenses/<id>/delete while logged out must redirect to /login (302)."""
        expense_id = _insert_expense(_registered_user["user_id"])

        response = client.post(
            f"/expenses/{expense_id}/delete",
            follow_redirects=False,
        )

        assert response.status_code == 302, (
            "Unauthenticated POST to delete URL must return 302"
        )
        assert LOGIN_URL in response.headers["Location"], (
            "Unauthenticated POST must redirect to /login"
        )

    def test_unauthenticated_post_does_not_delete_row(self, client, app, _registered_user):
        """An unauthenticated delete attempt must not modify the DB."""
        expense_id = _insert_expense(_registered_user["user_id"])

        client.post(
            f"/expenses/{expense_id}/delete",
            follow_redirects=False,
        )

        assert _expense_exists(expense_id), (
            "Unauthenticated POST must not remove the expense row from the DB"
        )


# ---------------------------------------------------------------------------
# 3. Route — authenticated, own expense (happy path)
# ---------------------------------------------------------------------------

class TestDeleteRouteHappyPath:

    def test_authenticated_post_own_expense_returns_302(
        self, auth_client, app, _registered_user
    ):
        """POST for own expense must return 302."""
        expense_id = _insert_expense(_registered_user["user_id"], title="My lunch")

        response = auth_client.post(
            f"/expenses/{expense_id}/delete",
            follow_redirects=False,
        )

        assert response.status_code == 302, (
            "Authenticated POST on own expense must redirect (302)"
        )

    def test_authenticated_post_own_expense_redirects_to_profile(
        self, auth_client, app, _registered_user
    ):
        """POST for own expense must redirect to /profile."""
        expense_id = _insert_expense(_registered_user["user_id"], title="My dinner")

        response = auth_client.post(
            f"/expenses/{expense_id}/delete",
            follow_redirects=False,
        )

        assert PROFILE_URL in response.headers["Location"], (
            "Redirect after successful delete must target /profile"
        )

    def test_authenticated_post_own_expense_removes_row_from_db(
        self, auth_client, app, _registered_user
    ):
        """After a successful delete, the DB row must no longer exist."""
        expense_id = _insert_expense(_registered_user["user_id"], title="Coffee to delete")

        auth_client.post(
            f"/expenses/{expense_id}/delete",
            follow_redirects=False,
        )

        assert not _expense_exists(expense_id), (
            "Expense row must be absent from DB after a successful authenticated delete"
        )

    def test_deleted_expense_absent_from_profile_page(
        self, auth_client, app, _registered_user
    ):
        """After deletion, the expense description must not appear on /profile."""
        title = "Unique Delete Verify Title XYZ"
        expense_id = _insert_expense(_registered_user["user_id"], title=title)

        auth_client.post(f"/expenses/{expense_id}/delete", follow_redirects=True)

        profile_response = auth_client.get(PROFILE_URL)
        assert title.encode() not in profile_response.data, (
            "Deleted expense title must not appear in the transaction list on /profile"
        )

    def test_delete_does_not_remove_sibling_expenses(
        self, auth_client, app, _registered_user
    ):
        """Deleting one expense must leave the user's other expenses on /profile."""
        id_to_delete = _insert_expense(
            _registered_user["user_id"], title="Gone expense"
        )
        _insert_expense(
            _registered_user["user_id"], title="Remaining expense", amount=999.0
        )

        auth_client.post(f"/expenses/{id_to_delete}/delete", follow_redirects=False)

        profile_response = auth_client.get(PROFILE_URL)
        assert b"Remaining expense" in profile_response.data, (
            "Non-deleted expense must still appear on /profile after a sibling is deleted"
        )


# ---------------------------------------------------------------------------
# 4. Route — authenticated, another user's expense (ownership guard)
# ---------------------------------------------------------------------------

class TestDeleteRouteOwnershipGuard:

    def test_authenticated_post_other_users_expense_returns_404(
        self, auth_client, app, _registered_user, _second_user
    ):
        """POST on an expense owned by a different user must return 404."""
        other_expense_id = _insert_expense(
            _second_user["user_id"], title="Other user expense"
        )

        response = auth_client.post(
            f"/expenses/{other_expense_id}/delete",
            follow_redirects=False,
        )

        assert response.status_code == 404, (
            "POST on another user's expense must return 404"
        )

    def test_authenticated_post_other_users_expense_leaves_row_in_db(
        self, auth_client, app, _registered_user, _second_user
    ):
        """The other user's expense row must remain in DB after a failed ownership check."""
        other_expense_id = _insert_expense(
            _second_user["user_id"], title="Should not be deleted"
        )

        auth_client.post(
            f"/expenses/{other_expense_id}/delete",
            follow_redirects=False,
        )

        assert _expense_exists(other_expense_id), (
            "Other user's expense row must still exist in DB after an unauthorised delete attempt"
        )


# ---------------------------------------------------------------------------
# 5. Route — authenticated, non-existent expense id
# ---------------------------------------------------------------------------

class TestDeleteRouteNonExistentId:

    def test_authenticated_post_nonexistent_id_returns_404(
        self, auth_client, app, _registered_user
    ):
        """POST to /expenses/999999/delete must return 404 when that id does not exist."""
        nonexistent_id = 999999

        response = auth_client.post(
            f"/expenses/{nonexistent_id}/delete",
            follow_redirects=False,
        )

        assert response.status_code == 404, (
            "POST for a non-existent expense id must return 404"
        )


# ---------------------------------------------------------------------------
# 6. HTTP semantics — GET returns 405 Method Not Allowed
# ---------------------------------------------------------------------------

class TestDeleteRouteHttpMethod:

    def test_get_to_delete_url_returns_405(self, auth_client, app, _registered_user):
        """GET /expenses/<id>/delete must return 405 (route is POST-only)."""
        expense_id = _insert_expense(_registered_user["user_id"])

        response = auth_client.get(
            f"/expenses/{expense_id}/delete",
            follow_redirects=False,
        )

        assert response.status_code == 405, (
            "GET to the delete URL must return 405 — route only accepts POST"
        )

    def test_get_to_any_delete_url_returns_405(self, auth_client):
        """GET to any delete URL (even non-existent id) must return 405, not 404.

        Flask checks the method before calling the view function, so 405 always
        takes precedence over 404 when the route exists but the method is wrong.
        """
        response = auth_client.get(
            "/expenses/999999/delete",
            follow_redirects=False,
        )

        assert response.status_code == 405, (
            "GET to a delete URL must always return 405 regardless of whether the id exists"
        )


# ---------------------------------------------------------------------------
# 7. UI — profile page shows Delete button and form per expense row
# ---------------------------------------------------------------------------

class TestProfileDeleteUI:

    def test_profile_shows_delete_button_when_expenses_exist(
        self, auth_client, app, _registered_user
    ):
        """The profile page must render a Delete button for each expense row."""
        _insert_expense(_registered_user["user_id"], title="Expense With Delete Button")

        response = auth_client.get(PROFILE_URL)

        assert b"Delete" in response.data, (
            "Profile page must contain a 'Delete' button when the user has expenses"
        )

    def test_profile_delete_form_action_points_to_correct_url(
        self, auth_client, app, _registered_user
    ):
        """The delete form's action attribute must point to /expenses/<id>/delete."""
        expense_id = _insert_expense(
            _registered_user["user_id"], title="Check delete action URL"
        )

        response = auth_client.get(PROFILE_URL)
        expected_action = f"/expenses/{expense_id}/delete".encode()

        assert expected_action in response.data, (
            f"Profile page must contain a form with action='/expenses/{expense_id}/delete'"
        )

    def test_profile_delete_form_uses_post_method(
        self, auth_client, app, _registered_user
    ):
        """The delete form must declare method='POST' (the route rejects GET with 405)."""
        _insert_expense(_registered_user["user_id"])

        response = auth_client.get(PROFILE_URL)
        html = response.data.decode("utf-8")

        assert 'method="POST"' in html or "method='POST'" in html, (
            "Delete form on profile page must use method='POST'"
        )

    def test_profile_shows_delete_action_for_each_expense(
        self, auth_client, app, _registered_user
    ):
        """Each expense row must have its own delete action URL."""
        id_a = _insert_expense(
            _registered_user["user_id"], title="Expense A", amount=100.0
        )
        id_b = _insert_expense(
            _registered_user["user_id"], title="Expense B", amount=200.0
        )

        response = auth_client.get(PROFILE_URL)

        assert f"/expenses/{id_a}/delete".encode() in response.data, (
            "Delete action URL for expense A must be present on the profile page"
        )
        assert f"/expenses/{id_b}/delete".encode() in response.data, (
            "Delete action URL for expense B must be present on the profile page"
        )

    def test_profile_extends_base_html(self, auth_client):
        """Profile page must extend base.html — verified by nav brand presence."""
        response = auth_client.get(PROFILE_URL)

        assert b"Spendly" in response.data, (
            "Profile page must extend base.html (nav brand 'Spendly' must appear)"
        )
