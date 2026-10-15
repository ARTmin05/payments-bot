"""Заказы в SQLite. Статусы: created → paid → (refunded) или created → expired."""

import sqlite3
from datetime import datetime
from pathlib import Path

DB = Path(__file__).parent / "orders.db"


def _conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, username TEXT, product TEXT,
            method TEXT, amount TEXT, status TEXT,
            invoice_id TEXT, charge_id TEXT,
            created TEXT, paid TEXT)""")


def create(user_id, username, product, method, amount, invoice_id=None) -> int:
    with _conn() as c:
        return c.execute(
            "INSERT INTO orders (user_id, username, product, method, amount, status, invoice_id, created) "
            "VALUES (?, ?, ?, ?, ?, 'created', ?, ?)",
            (user_id, username, product, method, str(amount), invoice_id, datetime.now().isoformat(timespec="seconds")),
        ).lastrowid


def mark_paid(order_id: int, charge_id: str | None = None) -> bool:
    """True — если заказ перешёл в paid именно сейчас. Повторное уведомление об оплате товар второй раз не выдаст."""
    with _conn() as c:
        return c.execute(
            "UPDATE orders SET status = 'paid', paid = ?, charge_id = COALESCE(?, charge_id) "
            "WHERE id = ? AND status = 'created'",
            (datetime.now().isoformat(timespec="seconds"), charge_id, order_id),
        ).rowcount == 1


def set_invoice(order_id: int, invoice_id: str):
    with _conn() as c:
        c.execute("UPDATE orders SET invoice_id = ? WHERE id = ?", (invoice_id, order_id))


def mark(order_id: int, status: str):
    with _conn() as c:
        c.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))


def get(order_id: int) -> sqlite3.Row | None:
    with _conn() as c:
        return c.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def pending_crypto() -> list[sqlite3.Row]:
    with _conn() as c:
        return c.execute("SELECT * FROM orders WHERE method = 'usdt' AND status = 'created'").fetchall()


def stats() -> list[sqlite3.Row]:
    with _conn() as c:
        return c.execute("SELECT method, status, COUNT(*) AS n, SUM(CAST(amount AS REAL)) AS total "
                         "FROM orders GROUP BY method, status ORDER BY method, status").fetchall()


def recent(limit: int = 10) -> list[sqlite3.Row]:
    with _conn() as c:
        return c.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
