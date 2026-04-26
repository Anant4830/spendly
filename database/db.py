import os
import sqlite3

from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "spendly.db")


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
