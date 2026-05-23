import os
import sqlite3

from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "spendly.db"),
)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER   PRIMARY KEY AUTOINCREMENT,
            name          TEXT      NOT NULL,
            email         TEXT      UNIQUE NOT NULL,
            password_hash TEXT      NOT NULL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id         INTEGER   PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER   NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title      TEXT      NOT NULL,
            amount     REAL      NOT NULL,
            category   TEXT      NOT NULL CHECK(category IN (
                           'Food','Transport','Shopping','Bills',
                           'Entertainment','Health','Other')),
            date       TEXT      NOT NULL,
            note       TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        conn.close()
        return

    # demo@spendly.com / demo1234
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo1234")),
    )
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    sample_expenses = [
        (user_id, "Lunch at café",     450.00,  "Food",          "2026-04-20", ""),
        (user_id, "Metro card top-up", 1200.00, "Transport",     "2026-04-19", ""),
        (user_id, "Electricity bill",  3500.00, "Bills",         "2026-04-18", "April bill"),
        (user_id, "Groceries",         2800.00, "Food",          "2026-04-17", ""),
        (user_id, "Movie tickets",     800.00,  "Entertainment", "2026-04-15", ""),
        (user_id, "Pharmacy",          650.00,  "Health",        "2026-04-14", ""),
        (user_id, "New headphones",    4999.00, "Shopping",      "2026-04-10", ""),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, title, amount, category, date, note) VALUES (?,?,?,?,?,?)",
        sample_expenses,
    )
    conn.commit()
    conn.close()


def get_user_by_email(email):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return row


def create_user(name, email, password_hash):
    conn = get_db()
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, password_hash),
    )
    conn.commit()
    user_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return user_id


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row


def get_recent_expenses(user_id, limit=10, from_date=None, to_date=None):
    conn = get_db()
    sql = ("SELECT id, title, amount, category, date FROM expenses "
           "WHERE user_id = ?")
    params = [user_id]
    if from_date is not None and to_date is not None:
        sql += " AND date BETWEEN ? AND ?"
        params += [from_date, to_date]
    sql += " ORDER BY date DESC, id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def get_category_breakdown(user_id, from_date=None, to_date=None):
    conn = get_db()
    sql = ("SELECT category, SUM(amount) AS total FROM expenses "
           "WHERE user_id = ?")
    params = [user_id]
    if from_date is not None and to_date is not None:
        sql += " AND date BETWEEN ? AND ?"
        params += [from_date, to_date]
    sql += " GROUP BY category ORDER BY total DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    grand_total = sum(r["total"] for r in rows) or 1
    return [
        {
            "name": r["category"],
            "amount": f"₹{r['total']:,.0f}",
            "pct": round(r["total"] / grand_total * 100),
        }
        for r in rows
    ]


def create_expense(user_id, title, amount, category, date, note):
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO expenses (user_id, title, amount, category, date, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, title, amount, category, date, note),
    )
    conn.commit()
    conn.close()
    return cursor.lastrowid


def get_expense_by_id(expense_id, user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
        (expense_id, user_id),
    ).fetchone()
    conn.close()
    return row


def update_expense(expense_id, user_id, title, amount, category, date, note):
    conn = get_db()
    conn.execute(
        "UPDATE expenses SET title=?, amount=?, category=?, date=?, note=? "
        "WHERE id=? AND user_id=?",
        (title, amount, category, date, note, expense_id, user_id),
    )
    conn.commit()
    conn.close()


def delete_expense(expense_id, user_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?",
        (expense_id, user_id),
    )
    conn.commit()
    conn.close()


def get_expense_stats(user_id, from_date=None, to_date=None):
    conn = get_db()
    date_clause = ""
    date_params = []
    if from_date is not None and to_date is not None:
        date_clause = " AND date BETWEEN ? AND ?"
        date_params = [from_date, to_date]

    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total_spent, COUNT(*) AS transaction_count "
        "FROM expenses WHERE user_id = ?" + date_clause,
        [user_id] + date_params,
    ).fetchone()
    top = conn.execute(
        "SELECT category FROM expenses WHERE user_id = ?" + date_clause +
        " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
        [user_id] + date_params,
    ).fetchone()
    conn.close()
    return {
        "total_spent": row["total_spent"],
        "transaction_count": row["transaction_count"],
        "top_category": top["category"] if top else "—",
    }
