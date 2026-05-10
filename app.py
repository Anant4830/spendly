import calendar
import sqlite3
from datetime import date, datetime

from flask import Flask, abort, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import (
    init_db, get_user_by_email, create_user,
    get_user_by_id, get_recent_expenses,
    get_expense_stats, get_category_breakdown,
)

app = Flask(__name__)
app.secret_key = "spendly-dev-secret"


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name     = request.form.get("name",     "").strip()
    email    = request.form.get("email",    "").strip()
    password = request.form.get("password", "").strip()

    if not name or not email or not password:
        return render_template("register.html",
                               error="All fields are required.",
                               name=name, email=email)

    if len(password) < 8:
        return render_template("register.html",
                               error="Password must be at least 8 characters.",
                               name=name, email=email)

    if get_user_by_email(email):
        return render_template("register.html",
                               error="An account with that email already exists.",
                               name=name, email=email)

    try:
        password_hash = generate_password_hash(password)
        user_id = create_user(name, email, password_hash)
        session["user_id"] = user_id
        return redirect(url_for("login"))
    except sqlite3.IntegrityError:
        return render_template("register.html",
                               error="An account with that email already exists.",
                               name=name, email=email)
    except Exception:
        return render_template("register.html",
                               error="Something went wrong. Please try again.",
                               name=name, email=email)


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email    = request.form.get("email",    "").strip()
    password = request.form.get("password", "").strip()

    if not email or not password:
        return render_template("login.html",
                               error="All fields are required.",
                               email=email)

    user = get_user_by_email(email)

    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html",
                               error="Invalid email or password.",
                               email=email)

    session["user_id"]   = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


def _months_ago(ref, n):
    total = ref.year * 12 + ref.month - 1 - n
    y, m = divmod(total, 12)
    m += 1
    d = min(ref.day, calendar.monthrange(y, m)[1])
    return date(y, m, d)


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    today = date.today()
    presets = [
        {"label": "This Month",    "key": "this_month",    "from_date": today.replace(day=1).isoformat(),       "to_date": today.isoformat()},
        {"label": "Last 3 Months", "key": "last_3_months", "from_date": _months_ago(today, 3).isoformat(),      "to_date": today.isoformat()},
        {"label": "Last 6 Months", "key": "last_6_months", "from_date": _months_ago(today, 6).isoformat(),      "to_date": today.isoformat()},
        {"label": "This Year",     "key": "this_year",     "from_date": date(today.year, 1, 1).isoformat(),     "to_date": today.isoformat()},
    ]

    raw_from = request.args.get("from", "").strip()
    raw_to   = request.args.get("to",   "").strip()

    if raw_from and raw_to:
        try:
            datetime.strptime(raw_from, "%Y-%m-%d")
            datetime.strptime(raw_to,   "%Y-%m-%d")
        except ValueError:
            abort(400)
        from_date, to_date = raw_from, raw_to
    else:
        from_date = to_date = None

    active_preset = next(
        (p["key"] for p in presets if from_date == p["from_date"] and to_date == p["to_date"]),
        None,
    )

    if from_date and to_date:
        if active_preset:
            filter_label = next(p["label"] for p in presets if p["key"] == active_preset)
        else:
            d_from = datetime.strptime(from_date, "%Y-%m-%d")
            d_to   = datetime.strptime(to_date,   "%Y-%m-%d")
            filter_label = f"{d_from.strftime('%d %b')} – {d_to.strftime('%d %b %Y')}"
    else:
        filter_label = "all time"

    raw_user = get_user_by_id(session["user_id"])
    name_parts = raw_user["name"].split()
    initials = (name_parts[0][0] + (name_parts[-1][0] if len(name_parts) > 1 else "")).upper()
    member_since = datetime.strptime(
        raw_user["created_at"][:10], "%Y-%m-%d"
    ).strftime("%B %Y")
    user = {
        "name": raw_user["name"],
        "email": raw_user["email"],
        "initials": initials,
        "member_since": member_since,
    }

    raw_stats = get_expense_stats(session["user_id"], from_date=from_date, to_date=to_date)
    stats = {
        "total_spent": f"₹{raw_stats['total_spent']:,.0f}",
        "transaction_count": raw_stats["transaction_count"],
        "top_category": raw_stats["top_category"],
    }

    raw_txns = get_recent_expenses(session["user_id"], limit=10, from_date=from_date, to_date=to_date)
    transactions = [
        {
            "date": datetime.strptime(t["date"], "%Y-%m-%d").strftime("%d %b %Y"),
            "description": t["title"],
            "category": t["category"],
            "amount": f"₹{t['amount']:,.0f}",
        }
        for t in raw_txns
    ]

    categories = get_category_breakdown(session["user_id"], from_date=from_date, to_date=to_date)

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        presets=presets,
        filter_dates={"from_date": from_date or "", "to_date": to_date or "", "active_preset": active_preset},
        filter_label=filter_label,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5001)
