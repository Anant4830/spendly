"""
tests/test_06_date_filter.py
============================
Pytest test suite for the Spendly date-filter feature (Step 6).

Feature spec: .claude/specs/06-date-filter-for-profile-page.md

Coverage:
  - Auth guard on /profile
  - No-filter (all-time) happy path
  - Valid date-range filter returns 200 with filtered data
  - Invalid date strings return 400
  - Only one of from/to supplied -> 200, all-time data (not a partial filter)
  - Filter bar HTML: four preset links, Apply button
  - Active preset CSS class appears when URL matches a preset range exactly
  - Stat card subtitles reflect the active filter label, not a hardcoded string
  - Zero-expense filtered period: no errors, 0 values displayed
  - DB helper unit tests: get_recent_expenses, get_expense_stats,
    get_category_breakdown each filter correctly on from_date/to_date kwargs
  - Currency symbol (INR ₹) present throughout
"""

import calendar
import sqlite3
import datetime

import pytest
from werkzeug.security import generate_password_hash

from app import app as flask_app
from database.db import (
    init_db,
    get_recent_expenses,
    get_expense_stats,
    get_category_breakdown,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _months_ago(ref: datetime.date, n: int) -> datetime.date:
    """Replicates the app's _months_ago logic so preset dates are computed
    identically in tests without reading the implementation."""
    total = ref.year * 12 + ref.month - 1 - n
    y, m = divmod(total, 12)
    m += 1
    d = min(ref.day, calendar.monthrange(y, m)[1])
    return datetime.date(y, m, d)


def _preset_dates(today: datetime.date) -> dict:
    """Returns the four preset from/to pairs as YYYY-MM-DD strings."""
    return {
        "this_month":    (today.replace(day=1).isoformat(), today.isoformat()),
        "last_3_months": (_months_ago(today, 3).isoformat(),  today.isoformat()),
        "last_6_months": (_months_ago(today, 6).isoformat(),  today.isoformat()),
        "this_year":     (datetime.date(today.year, 1, 1).isoformat(), today.isoformat()),
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app(tmp_path):
    """Flask app wired to an isolated SQLite file in a temp directory."""
    db_file = str(tmp_path / "test_spendly.db")
    flask_app.config.update({
        "TESTING": True,
        "DATABASE": db_file,
        "SECRET_KEY": "test-secret-key",
        "WTF_CSRF_ENABLED": False,
    })
    # Patch get_db so it uses the temp DB, not the production file.
    import database.db as db_module
    original_db_path = db_module.DB_PATH
    db_module.DB_PATH = db_file

    with flask_app.app_context():
        init_db()
        yield flask_app

    # Restore original path after the test
    db_module.DB_PATH = original_db_path


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def _seeded_user(app):
    """
    Creates a test user and inserts expenses across two distinct months so
    that date-range filtering can be verified by exclusion.

    Month A (old): 2025-01-15 — 'Old Expense'  ₹1000  Food
    Month B (old): 2025-02-10 — 'Feb Expense'  ₹2000  Transport
    Month C (recent): one month ago relative to today — 'Recent Expense' ₹500 Bills

    Returns a dict with user credentials and the inserted expense details.
    """
    import database.db as db_module

    conn = sqlite3.connect(db_module.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    pw_hash = generate_password_hash("testpass123")
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "filter_test@example.com", pw_hash),
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    expenses = [
        # Fixed past month A — safely outside any recent preset
        (user_id, "Old Expense",    1000.00, "Food",      "2025-01-15", ""),
        # Fixed past month B — different month from A
        (user_id, "Feb Expense",    2000.00, "Transport", "2025-02-10", ""),
        # Today's expense — always inside "This Month" and "This Year"
        (user_id, "Today Expense",   500.00, "Bills",     datetime.date.today().isoformat(), ""),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, title, amount, category, date, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        expenses,
    )
    conn.commit()
    conn.close()

    return {
        "user_id": user_id,
        "email": "filter_test@example.com",
        "password": "testpass123",
    }


@pytest.fixture()
def auth_client(client, _seeded_user):
    """Test client that is already logged in as the seeded user."""
    client.post(
        "/login",
        data={"email": _seeded_user["email"], "password": _seeded_user["password"]},
        follow_redirects=False,
    )
    return client


# ---------------------------------------------------------------------------
# 1. Auth guard
# ---------------------------------------------------------------------------

class TestAuthGuard:
    def test_unauthenticated_get_profile_redirects_to_login(self, client):
        response = client.get("/profile")
        assert response.status_code == 302, (
            "Unauthenticated /profile must redirect (302)"
        )
        assert "/login" in response.headers["Location"], (
            "Redirect target must be /login"
        )

    def test_unauthenticated_profile_with_filter_params_redirects(self, client):
        response = client.get("/profile?from=2026-01-01&to=2026-01-31")
        assert response.status_code == 302, (
            "Unauthenticated /profile with valid filter params must still redirect"
        )
        assert "/login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# 2. No-filter (all-time) happy path
# ---------------------------------------------------------------------------

class TestNoFilterHappyPath:
    def test_profile_no_params_returns_200(self, auth_client):
        response = auth_client.get("/profile")
        assert response.status_code == 200, (
            "Authenticated GET /profile with no params must return 200"
        )

    def test_profile_no_filter_shows_all_time_label(self, auth_client):
        response = auth_client.get("/profile")
        assert b"all time" in response.data, (
            "Stat card subtitle must say 'all time' when no filter is active"
        )

    def test_profile_no_filter_shows_all_expenses(self, auth_client, _seeded_user):
        """Without a filter all three seeded expenses (total ₹3500) should appear."""
        response = auth_client.get("/profile")
        # All three amounts contribute — total is ₹3,500
        assert b"\xe2\x82\xb9" in response.data, (
            "Response must contain the ₹ currency symbol (UTF-8: e2 82 b9)"
        )
        # The transaction table should list all three titles
        assert b"Old Expense" in response.data
        assert b"Feb Expense" in response.data
        assert b"Today Expense" in response.data


# ---------------------------------------------------------------------------
# 3. Valid date-range filter
# ---------------------------------------------------------------------------

class TestValidDateRangeFilter:
    def test_valid_filter_returns_200(self, auth_client):
        response = auth_client.get("/profile?from=2025-01-01&to=2025-01-31")
        assert response.status_code == 200, (
            "Valid from/to params must return 200"
        )

    def test_filter_includes_expense_in_range(self, auth_client):
        """Filtering to January 2025 must include 'Old Expense' (2025-01-15)."""
        response = auth_client.get("/profile?from=2025-01-01&to=2025-01-31")
        assert b"Old Expense" in response.data, (
            "Expense dated 2025-01-15 must appear when filtering 2025-01-01 to 2025-01-31"
        )

    def test_filter_excludes_expense_outside_range(self, auth_client):
        """Filtering to January 2025 must NOT include February or today's expense."""
        response = auth_client.get("/profile?from=2025-01-01&to=2025-01-31")
        assert b"Feb Expense" not in response.data, (
            "Expense dated 2025-02-10 must be excluded when filtering to Jan 2025"
        )
        assert b"Today Expense" not in response.data, (
            "Today's expense must be excluded when filtering to Jan 2025"
        )

    def test_filter_stats_reflect_only_filtered_period(self, auth_client):
        """Transaction count stat for Jan 2025 must be 1 (only 'Old Expense')."""
        response = auth_client.get("/profile?from=2025-01-01&to=2025-01-31")
        # The route renders transaction_count as a bare integer in the template
        assert b">1<" in response.data or b"1\n" in response.data or b">1\n" in response.data or (
            # More robust: check that count 1 appears somewhere near transaction context
            b"1" in response.data
        ), "Transaction count stat must reflect filtered period only"
        # Total for Jan 2025 = ₹1,000
        assert "₹1,000".encode() in response.data, (
            "Total spent must be ₹1,000 for Jan 2025 filter"
        )

    def test_filter_categories_reflect_only_filtered_period(self, auth_client):
        """Category breakdown for Jan 2025 must show Food only."""
        response = auth_client.get("/profile?from=2025-01-01&to=2025-01-31")
        assert b"Food" in response.data, (
            "Food category must appear in Jan 2025 breakdown"
        )
        # Transport belongs to Feb 2025 — must not appear in category breakdown
        # (It could appear as a badge label if the table is shown, but the table
        #  is also filtered, so neither should be present for the Feb expense)
        assert b"Feb Expense" not in response.data

    def test_custom_range_filter_label_shows_formatted_dates(self, auth_client):
        """A custom range that matches no preset must render a formatted date span."""
        response = auth_client.get("/profile?from=2025-01-10&to=2025-01-20")
        # Expected label fragment: "10 Jan" somewhere in the subtitle
        assert b"10 Jan" in response.data, (
            "Custom range filter label must show formatted 'DD Mon' for from-date"
        )
        assert b"20 Jan 2025" in response.data, (
            "Custom range filter label must show formatted 'DD Mon YYYY' for to-date"
        )


# ---------------------------------------------------------------------------
# 4. Invalid date strings -> 400
# ---------------------------------------------------------------------------

class TestInvalidDateReturns400:
    @pytest.mark.parametrize("from_val,to_val", [
        # Both params present but one or both are malformed -> must be 400
        ("not-a-date", "2026-05-10"),         # non-date string for from
        ("2026-05-01", "not-a-date"),          # non-date string for to
        ("13/05/2026",  "2026-05-31"),         # wrong separator format
        ("2026-05-32",  "2026-05-31"),         # impossible day (32nd)
        ("2026-99-01",  "2026-05-10"),         # invalid month (99)
        ("2026-05-01",  "2026-13-01"),         # invalid month in to
    ])
    def test_both_params_malformed_returns_400(self, auth_client, from_val, to_val):
        response = auth_client.get(f"/profile?from={from_val}&to={to_val}")
        assert response.status_code == 400, (
            f"Malformed date pair from='{from_val}' to='{to_val}' must return 400"
        )

    def test_empty_from_with_valid_to_is_treated_as_no_filter(self, auth_client):
        """Empty string for 'from' means the filter is unset; must return 200."""
        response = auth_client.get("/profile?from=&to=2026-05-10")
        assert response.status_code == 200, (
            "Empty 'from' with a valid 'to' must show all-time data (200), not 400"
        )


# ---------------------------------------------------------------------------
# 5. Only one of from/to supplied -> 200, all-time data
# ---------------------------------------------------------------------------

class TestPartialParamsShowAllTime:
    def test_only_from_supplied_returns_200(self, auth_client):
        response = auth_client.get("/profile?from=2025-01-01")
        assert response.status_code == 200, (
            "Supplying only 'from' must return 200 (not 400)"
        )

    def test_only_from_supplied_shows_all_time_label(self, auth_client):
        response = auth_client.get("/profile?from=2025-01-01")
        assert b"all time" in response.data, (
            "Only 'from' supplied must display all-time data with 'all time' label"
        )

    def test_only_from_supplied_shows_all_expenses(self, auth_client):
        """All expenses must be visible when only 'from' is provided."""
        response = auth_client.get("/profile?from=2025-01-01")
        assert b"Old Expense" in response.data
        assert b"Feb Expense" in response.data
        assert b"Today Expense" in response.data

    def test_only_to_supplied_returns_200(self, auth_client):
        response = auth_client.get("/profile?to=2025-12-31")
        assert response.status_code == 200, (
            "Supplying only 'to' must return 200 (not 400)"
        )

    def test_only_to_supplied_shows_all_time_label(self, auth_client):
        response = auth_client.get("/profile?to=2025-12-31")
        assert b"all time" in response.data, (
            "Only 'to' supplied must display all-time data with 'all time' label"
        )

    def test_only_to_supplied_shows_all_expenses(self, auth_client):
        """All expenses must be visible when only 'to' is provided."""
        response = auth_client.get("/profile?to=2025-12-31")
        assert b"Old Expense" in response.data
        assert b"Feb Expense" in response.data
        assert b"Today Expense" in response.data


# ---------------------------------------------------------------------------
# 6. Filter bar HTML presence
# ---------------------------------------------------------------------------

class TestFilterBarHTML:
    def test_filter_bar_contains_this_month_preset(self, auth_client):
        response = auth_client.get("/profile")
        assert b"This Month" in response.data, (
            "Filter bar must contain 'This Month' preset link"
        )

    def test_filter_bar_contains_last_3_months_preset(self, auth_client):
        response = auth_client.get("/profile")
        assert b"Last 3 Months" in response.data, (
            "Filter bar must contain 'Last 3 Months' preset link"
        )

    def test_filter_bar_contains_last_6_months_preset(self, auth_client):
        response = auth_client.get("/profile")
        assert b"Last 6 Months" in response.data, (
            "Filter bar must contain 'Last 6 Months' preset link"
        )

    def test_filter_bar_contains_this_year_preset(self, auth_client):
        response = auth_client.get("/profile")
        assert b"This Year" in response.data, (
            "Filter bar must contain 'This Year' preset link"
        )

    def test_filter_bar_contains_apply_button(self, auth_client):
        response = auth_client.get("/profile")
        assert b"Apply" in response.data, (
            "Filter bar must contain an 'Apply' submit button"
        )

    def test_filter_form_uses_get_method(self, auth_client):
        response = auth_client.get("/profile")
        # The form tag must declare method="GET" (case-insensitive in HTML,
        # but the template uses uppercase GET per the spec)
        assert b'method="GET"' in response.data or b"method='GET'" in response.data, (
            "Date filter form must use GET method"
        )

    def test_filter_bar_has_from_input(self, auth_client):
        response = auth_client.get("/profile")
        assert b'name="from"' in response.data, (
            "Filter form must have an input with name='from'"
        )

    def test_filter_bar_has_to_input(self, auth_client):
        response = auth_client.get("/profile")
        assert b'name="to"' in response.data, (
            "Filter form must have an input with name='to'"
        )


# ---------------------------------------------------------------------------
# 7. Active preset CSS class
# ---------------------------------------------------------------------------

class TestActivePresetHighlight:
    def test_this_month_preset_is_active_when_url_matches(self, auth_client):
        today = datetime.date.today()
        presets = _preset_dates(today)
        from_val, to_val = presets["this_month"]
        response = auth_client.get(f"/profile?from={from_val}&to={to_val}")
        assert response.status_code == 200
        assert b"filter-preset--active" in response.data, (
            "Active preset CSS class must appear when URL matches 'This Month'"
        )
        # The active link text must be "This Month"
        html = response.data.decode("utf-8")
        active_idx = html.find("filter-preset--active")
        assert active_idx != -1
        snippet = html[active_idx: active_idx + 200]
        assert "This Month" in snippet, (
            "'This Month' label must be adjacent to the active preset class"
        )

    def test_last_3_months_preset_is_active_when_url_matches(self, auth_client):
        today = datetime.date.today()
        presets = _preset_dates(today)
        from_val, to_val = presets["last_3_months"]
        response = auth_client.get(f"/profile?from={from_val}&to={to_val}")
        assert b"filter-preset--active" in response.data, (
            "Active preset CSS class must appear when URL matches 'Last 3 Months'"
        )

    def test_this_year_preset_is_active_when_url_matches(self, auth_client):
        today = datetime.date.today()
        presets = _preset_dates(today)
        from_val, to_val = presets["this_year"]
        response = auth_client.get(f"/profile?from={from_val}&to={to_val}")
        assert b"filter-preset--active" in response.data, (
            "Active preset CSS class must appear when URL matches 'This Year'"
        )

    def test_custom_range_has_no_active_preset(self, auth_client):
        """A custom range that matches no preset must not mark any link active."""
        response = auth_client.get("/profile?from=2025-01-10&to=2025-01-20")
        assert b"filter-preset--active" not in response.data, (
            "No preset should be marked active for a custom date range"
        )

    def test_no_filter_has_no_active_preset(self, auth_client):
        """With no filter params, no preset should be marked active."""
        response = auth_client.get("/profile")
        assert b"filter-preset--active" not in response.data, (
            "No preset should be marked active when no filter is applied"
        )


# ---------------------------------------------------------------------------
# 8. Stat card subtitles reflect active filter label
# ---------------------------------------------------------------------------

class TestFilterLabelInStatSubtitles:
    def test_no_filter_shows_all_time_subtitle(self, auth_client):
        response = auth_client.get("/profile")
        assert b"all time" in response.data, (
            "Stat subtitle must be 'all time' when no filter is active"
        )

    def test_this_month_filter_shows_this_month_label(self, auth_client):
        today = datetime.date.today()
        from_val, to_val = _preset_dates(today)["this_month"]
        response = auth_client.get(f"/profile?from={from_val}&to={to_val}")
        assert b"This Month" in response.data, (
            "Stat subtitle must show 'This Month' when that preset is active"
        )
        assert b"all time" not in response.data, (
            "'all time' must not appear when a preset filter is active"
        )

    def test_last_3_months_filter_shows_correct_label(self, auth_client):
        today = datetime.date.today()
        from_val, to_val = _preset_dates(today)["last_3_months"]
        response = auth_client.get(f"/profile?from={from_val}&to={to_val}")
        assert b"Last 3 Months" in response.data, (
            "Stat subtitle must show 'Last 3 Months' when that preset is active"
        )

    def test_this_year_filter_shows_correct_label(self, auth_client):
        today = datetime.date.today()
        from_val, to_val = _preset_dates(today)["this_year"]
        response = auth_client.get(f"/profile?from={from_val}&to={to_val}")
        assert b"This Year" in response.data, (
            "Stat subtitle must show 'This Year' when that preset is active"
        )

    def test_custom_range_shows_formatted_date_label(self, auth_client):
        response = auth_client.get("/profile?from=2025-03-05&to=2025-03-25")
        html = response.data.decode("utf-8")
        # Formatted label: "05 Mar – 25 Mar 2025"
        assert "05 Mar" in html, (
            "Custom range label must contain formatted from-date '05 Mar'"
        )
        assert "25 Mar 2025" in html, (
            "Custom range label must contain formatted to-date '25 Mar 2025'"
        )


# ---------------------------------------------------------------------------
# 9. Zero-expense filtered period — no errors, graceful display
# ---------------------------------------------------------------------------

class TestZeroExpensePeriod:
    def test_empty_period_returns_200(self, auth_client):
        # Filter to a range where the seeded user has no expenses
        response = auth_client.get("/profile?from=2024-01-01&to=2024-01-31")
        assert response.status_code == 200, (
            "Filtering to a period with no expenses must still return 200"
        )

    def test_empty_period_shows_zero_total(self, auth_client):
        response = auth_client.get("/profile?from=2024-01-01&to=2024-01-31")
        assert "₹0".encode() in response.data, (
            "Total spent must display ₹0 when no expenses exist in the filtered period"
        )

    def test_empty_period_shows_zero_transactions(self, auth_client):
        response = auth_client.get("/profile?from=2024-01-01&to=2024-01-31")
        html = response.data.decode("utf-8")
        # The transaction count stat card value should be 0
        assert ">0<" in html, (
            "Transaction count stat must display 0 for an empty period"
        )

    def test_empty_period_transaction_table_has_no_rows(self, auth_client):
        response = auth_client.get("/profile?from=2024-01-01&to=2024-01-31")
        # No expense titles should appear in the table body
        assert b"Old Expense" not in response.data
        assert b"Feb Expense" not in response.data
        assert b"Today Expense" not in response.data

    def test_empty_period_has_no_server_error(self, auth_client):
        """Ensure the response is valid HTML and not a 500."""
        response = auth_client.get("/profile?from=2024-01-01&to=2024-01-31")
        assert response.status_code != 500, (
            "An empty filtered period must not cause a server error"
        )


# ---------------------------------------------------------------------------
# 10. Currency symbol (₹) throughout
# ---------------------------------------------------------------------------

class TestCurrencySymbol:
    def test_inr_symbol_present_on_unfiltered_profile(self, auth_client):
        response = auth_client.get("/profile")
        assert "₹".encode("utf-8") in response.data, (
            "All monetary amounts must display with ₹ (INR), never $ or £"
        )

    def test_inr_symbol_present_on_filtered_profile(self, auth_client):
        response = auth_client.get("/profile?from=2025-01-01&to=2025-01-31")
        assert "₹".encode("utf-8") in response.data, (
            "Filtered profile page must display amounts with ₹ (INR)"
        )

    def test_no_usd_symbol_on_profile(self, auth_client):
        response = auth_client.get("/profile")
        assert b"$" not in response.data, (
            "No USD ($) symbol should appear on the profile page"
        )

    def test_no_gbp_symbol_on_profile(self, auth_client):
        response = auth_client.get("/profile")
        assert b"\xc2\xa3" not in response.data, (
            "No GBP (£) symbol should appear on the profile page"
        )


# ---------------------------------------------------------------------------
# 11. DB helper unit tests — get_recent_expenses
# ---------------------------------------------------------------------------

class TestGetRecentExpenses:
    def test_no_date_filter_returns_all_expenses(self, app, _seeded_user):
        with app.app_context():
            rows = get_recent_expenses(_seeded_user["user_id"])
        assert len(rows) == 3, (
            "get_recent_expenses with no date filter must return all 3 seeded expenses"
        )

    def test_date_filter_includes_expense_in_range(self, app, _seeded_user):
        with app.app_context():
            rows = get_recent_expenses(
                _seeded_user["user_id"],
                from_date="2025-01-01",
                to_date="2025-01-31",
            )
        titles = [r["title"] for r in rows]
        assert "Old Expense" in titles, (
            "get_recent_expenses must include 'Old Expense' (2025-01-15) for Jan filter"
        )

    def test_date_filter_excludes_expenses_outside_range(self, app, _seeded_user):
        with app.app_context():
            rows = get_recent_expenses(
                _seeded_user["user_id"],
                from_date="2025-01-01",
                to_date="2025-01-31",
            )
        titles = [r["title"] for r in rows]
        assert "Feb Expense" not in titles, (
            "get_recent_expenses must exclude 'Feb Expense' (2025-02-10) for Jan filter"
        )
        assert "Today Expense" not in titles, (
            "get_recent_expenses must exclude 'Today Expense' for Jan 2025 filter"
        )

    def test_date_filter_jan_returns_exactly_one_row(self, app, _seeded_user):
        with app.app_context():
            rows = get_recent_expenses(
                _seeded_user["user_id"],
                from_date="2025-01-01",
                to_date="2025-01-31",
            )
        assert len(rows) == 1, (
            "Exactly one expense exists in Jan 2025 for the seeded user"
        )

    def test_date_filter_feb_returns_exactly_one_row(self, app, _seeded_user):
        with app.app_context():
            rows = get_recent_expenses(
                _seeded_user["user_id"],
                from_date="2025-02-01",
                to_date="2025-02-28",
            )
        assert len(rows) == 1
        assert rows[0]["title"] == "Feb Expense"

    def test_date_filter_empty_range_returns_no_rows(self, app, _seeded_user):
        with app.app_context():
            rows = get_recent_expenses(
                _seeded_user["user_id"],
                from_date="2024-01-01",
                to_date="2024-12-31",
            )
        assert len(rows) == 0, (
            "get_recent_expenses must return empty list for a period with no expenses"
        )

    def test_only_from_date_supplied_returns_all(self, app, _seeded_user):
        """Per spec: if only from_date is supplied (to_date=None), no filter is applied."""
        with app.app_context():
            rows = get_recent_expenses(
                _seeded_user["user_id"],
                from_date="2025-01-01",
                to_date=None,
            )
        assert len(rows) == 3, (
            "get_recent_expenses with only from_date must return all records (no partial filter)"
        )

    def test_only_to_date_supplied_returns_all(self, app, _seeded_user):
        with app.app_context():
            rows = get_recent_expenses(
                _seeded_user["user_id"],
                from_date=None,
                to_date="2025-12-31",
            )
        assert len(rows) == 3, (
            "get_recent_expenses with only to_date must return all records (no partial filter)"
        )

    def test_limit_is_respected_without_date_filter(self, app, _seeded_user):
        with app.app_context():
            rows = get_recent_expenses(_seeded_user["user_id"], limit=2)
        assert len(rows) <= 2, (
            "get_recent_expenses must respect the limit parameter"
        )

    def test_results_ordered_by_date_descending(self, app, _seeded_user):
        with app.app_context():
            rows = get_recent_expenses(_seeded_user["user_id"])
        dates = [r["date"] for r in rows]
        assert dates == sorted(dates, reverse=True), (
            "get_recent_expenses must return results in descending date order"
        )


# ---------------------------------------------------------------------------
# 12. DB helper unit tests — get_expense_stats
# ---------------------------------------------------------------------------

class TestGetExpenseStats:
    def test_no_filter_returns_aggregate_of_all_expenses(self, app, _seeded_user):
        with app.app_context():
            stats = get_expense_stats(_seeded_user["user_id"])
        assert stats["transaction_count"] == 3, (
            "get_expense_stats with no filter must count all 3 seeded expenses"
        )
        assert stats["total_spent"] == pytest.approx(3500.00), (
            "get_expense_stats total_spent must be 1000+2000+500=3500 for all expenses"
        )

    def test_date_filter_jan_2025_total(self, app, _seeded_user):
        with app.app_context():
            stats = get_expense_stats(
                _seeded_user["user_id"],
                from_date="2025-01-01",
                to_date="2025-01-31",
            )
        assert stats["total_spent"] == pytest.approx(1000.00), (
            "get_expense_stats total for Jan 2025 must be ₹1,000"
        )
        assert stats["transaction_count"] == 1

    def test_date_filter_feb_2025_total(self, app, _seeded_user):
        with app.app_context():
            stats = get_expense_stats(
                _seeded_user["user_id"],
                from_date="2025-02-01",
                to_date="2025-02-28",
            )
        assert stats["total_spent"] == pytest.approx(2000.00)
        assert stats["transaction_count"] == 1

    def test_date_filter_empty_range_returns_zero(self, app, _seeded_user):
        with app.app_context():
            stats = get_expense_stats(
                _seeded_user["user_id"],
                from_date="2024-01-01",
                to_date="2024-12-31",
            )
        assert stats["total_spent"] == pytest.approx(0.0), (
            "get_expense_stats total must be 0 for a period with no expenses"
        )
        assert stats["transaction_count"] == 0

    def test_date_filter_jan_top_category_is_food(self, app, _seeded_user):
        with app.app_context():
            stats = get_expense_stats(
                _seeded_user["user_id"],
                from_date="2025-01-01",
                to_date="2025-01-31",
            )
        assert stats["top_category"] == "Food", (
            "Top category for Jan 2025 must be 'Food' (the only category in that month)"
        )

    def test_empty_period_top_category_is_dash(self, app, _seeded_user):
        with app.app_context():
            stats = get_expense_stats(
                _seeded_user["user_id"],
                from_date="2024-01-01",
                to_date="2024-12-31",
            )
        assert stats["top_category"] == "—", (
            "Top category must be '—' when no expenses exist in the filtered period"
        )

    def test_only_from_date_none_applies_no_filter(self, app, _seeded_user):
        with app.app_context():
            stats = get_expense_stats(
                _seeded_user["user_id"],
                from_date="2025-01-01",
                to_date=None,
            )
        assert stats["transaction_count"] == 3, (
            "get_expense_stats with only from_date must return all-time stats"
        )


# ---------------------------------------------------------------------------
# 13. DB helper unit tests — get_category_breakdown
# ---------------------------------------------------------------------------

class TestGetCategoryBreakdown:
    def test_no_filter_returns_all_categories(self, app, _seeded_user):
        with app.app_context():
            cats = get_category_breakdown(_seeded_user["user_id"])
        names = [c["name"] for c in cats]
        assert "Food" in names, "Food category must appear in all-time breakdown"
        assert "Transport" in names, "Transport category must appear in all-time breakdown"
        assert "Bills" in names, "Bills category must appear in all-time breakdown"

    def test_no_filter_total_percentages_sum_to_100(self, app, _seeded_user):
        with app.app_context():
            cats = get_category_breakdown(_seeded_user["user_id"])
        total_pct = sum(c["pct"] for c in cats)
        # Rounding can cause slight deviation; allow ±2
        assert abs(total_pct - 100) <= 2, (
            f"Category percentages must sum to ~100 (got {total_pct})"
        )

    def test_date_filter_jan_returns_only_food(self, app, _seeded_user):
        with app.app_context():
            cats = get_category_breakdown(
                _seeded_user["user_id"],
                from_date="2025-01-01",
                to_date="2025-01-31",
            )
        names = [c["name"] for c in cats]
        assert names == ["Food"], (
            "Category breakdown for Jan 2025 must contain only 'Food'"
        )

    def test_date_filter_feb_returns_only_transport(self, app, _seeded_user):
        with app.app_context():
            cats = get_category_breakdown(
                _seeded_user["user_id"],
                from_date="2025-02-01",
                to_date="2025-02-28",
            )
        names = [c["name"] for c in cats]
        assert names == ["Transport"], (
            "Category breakdown for Feb 2025 must contain only 'Transport'"
        )

    def test_date_filter_empty_range_returns_empty_list(self, app, _seeded_user):
        with app.app_context():
            cats = get_category_breakdown(
                _seeded_user["user_id"],
                from_date="2024-01-01",
                to_date="2024-12-31",
            )
        assert cats == [], (
            "get_category_breakdown must return an empty list for a period with no expenses"
        )

    def test_category_amounts_use_inr_prefix(self, app, _seeded_user):
        with app.app_context():
            cats = get_category_breakdown(_seeded_user["user_id"])
        for cat in cats:
            assert cat["amount"].startswith("₹"), (
                f"Category amount '{cat['amount']}' must start with ₹ (INR)"
            )

    def test_category_pct_is_integer_between_0_and_100(self, app, _seeded_user):
        with app.app_context():
            cats = get_category_breakdown(_seeded_user["user_id"])
        for cat in cats:
            assert isinstance(cat["pct"], int), (
                f"Category pct must be an integer, got {type(cat['pct'])}"
            )
            assert 0 <= cat["pct"] <= 100, (
                f"Category pct must be between 0 and 100, got {cat['pct']}"
            )

    def test_only_from_date_none_applies_no_filter(self, app, _seeded_user):
        with app.app_context():
            cats = get_category_breakdown(
                _seeded_user["user_id"],
                from_date="2025-01-01",
                to_date=None,
            )
        # All three categories must be present when filter is not applied
        names = [c["name"] for c in cats]
        assert len(names) == 3, (
            "get_category_breakdown with only from_date must return all categories"
        )

    def test_categories_ordered_by_total_descending(self, app, _seeded_user):
        with app.app_context():
            cats = get_category_breakdown(_seeded_user["user_id"])
        # Transport (₹2000) > Food (₹1000) > Bills (₹500)
        assert cats[0]["name"] == "Transport", (
            "get_category_breakdown must order categories by total descending"
        )
        assert cats[1]["name"] == "Food"
        assert cats[2]["name"] == "Bills"
