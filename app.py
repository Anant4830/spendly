import sqlite3

from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import init_db, get_user_by_email, create_user

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


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "initials": "DU",
        "member_since": "April 2025",
    }

    stats = {
        "total_spent": "₹18,240",
        "transaction_count": 12,
        "top_category": "Food",
    }

    transactions = [
        {"date": "28 Apr 2025", "description": "Swiggy Order",        "category": "Food",          "amount": "₹450"},
        {"date": "27 Apr 2025", "description": "Ola Cab",              "category": "Transport",     "amount": "₹220"},
        {"date": "25 Apr 2025", "description": "Electricity Bill",     "category": "Bills",         "amount": "₹1,840"},
        {"date": "23 Apr 2025", "description": "Apollo Pharmacy",      "category": "Health",        "amount": "₹610"},
        {"date": "21 Apr 2025", "description": "Netflix Subscription", "category": "Entertainment", "amount": "₹649"},
        {"date": "19 Apr 2025", "description": "Zara T-shirt",         "category": "Shopping",      "amount": "₹1,299"},
        {"date": "17 Apr 2025", "description": "Zomato Order",         "category": "Food",          "amount": "₹380"},
    ]

    categories = [
        {"name": "Food",          "amount": "₹6,540", "pct": 36},
        {"name": "Bills",         "amount": "₹4,200", "pct": 23},
        {"name": "Transport",     "amount": "₹2,180", "pct": 12},
        {"name": "Entertainment", "amount": "₹1,800", "pct": 10},
        {"name": "Shopping",      "amount": "₹2,070", "pct": 11},
        {"name": "Health",        "amount": "₹1,450", "pct": 8},
    ]

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
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
