"""Small SQLite connection factory shared by repositories and data scripts."""

from __future__ import annotations

import os
if os.name == "nt":
    import msvcrt
else:
    import fcntl
import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from src.core.config import settings


@contextmanager
def database(*, readonly: bool = False) -> Iterator[sqlite3.Connection]:
    path = settings.database_path
    if not path.exists() and readonly:
        raise FileNotFoundError(f"فایل پایگاه داده پیدا نشد: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)

    target = f"file:{path}?mode=ro" if readonly else str(path)
    lock_context = database_write_lock(path) if not readonly else _no_lock()
    with lock_context:
        connection = sqlite3.connect(target, uri=readonly, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        if not readonly:
            ensure_inquiries_schema(connection)
        try:
            yield connection
            if not readonly:
                connection.commit()
        except Exception:
            if not readonly:
                connection.rollback()
            raise
        finally:
            connection.close()


def ensure_inquiries_schema(connection: sqlite3.Connection) -> None:
    """Ensure the inquiries table exists with all lifecycle and simulation columns."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS inquiries (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            shop_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            offer_id TEXT,
            channel TEXT NOT NULL DEFAULT 'panel',
            status TEXT NOT NULL,
            message TEXT,
            requests_json TEXT,
            answer_json TEXT,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            delivered_at TEXT,
            read_at TEXT,
            answered_at TEXT,
            expires_at TEXT,
            persona TEXT,
            simulated INTEGER DEFAULT 1,
            batch_id TEXT,
            payload_json TEXT
        )
        """
    )
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(inquiries)").fetchall()
    }
    columns_to_add = [
        ("session_id", "TEXT"),
        ("offer_id", "TEXT"),
        ("channel", "TEXT NOT NULL DEFAULT 'panel'"),
        ("message", "TEXT"),
        ("requests_json", "TEXT"),
        ("answer_json", "TEXT"),
        ("sent_at", "TEXT"),
        ("delivered_at", "TEXT"),
        ("read_at", "TEXT"),
        ("answered_at", "TEXT"),
        ("expires_at", "TEXT"),
        ("persona", "TEXT"),
        ("simulated", "INTEGER DEFAULT 1"),
        ("batch_id", "TEXT"),
        ("payload_json", "TEXT"),
    ]
    for col_name, col_def in columns_to_add:
        if col_name not in existing_columns:
            connection.execute(f"ALTER TABLE inquiries ADD COLUMN {col_name} {col_def}")



def ensure_price_checks_schema(connection: sqlite3.Connection) -> None:
    """Keep real buyer reports independent of dataset offers and Mock results."""
    connection.execute("""CREATE TABLE IF NOT EXISTS price_checks (
        id TEXT PRIMARY KEY, product_id TEXT NOT NULL, shop_id TEXT NOT NULL,
        offer_id TEXT, outcome TEXT NOT NULL, reported_price INTEGER,
        method TEXT NOT NULL, note TEXT, source TEXT NOT NULL DEFAULT 'buyer_report',
        checked_at TEXT NOT NULL, observed_at TEXT, in_stock INTEGER, session_id TEXT)""")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(price_checks)")}
    for name, definition in (("observed_at", "TEXT"), ("in_stock", "INTEGER"), ("session_id", "TEXT")):
        if name not in columns:
            connection.execute(f"ALTER TABLE price_checks ADD COLUMN {name} {definition}")


@contextmanager
def database_write_lock(database_path: Path, *, exclusive: bool = False):
    """Coordinate app writes with the loader's atomic database replacement."""
    lock_path = database_path.with_name(f"{database_path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        if os.name == "nt":
            # Windows byte-range locks need an existing byte and a stable offset.
            if lock_file.seek(0, 2) == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            if os.name == "nt":
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def _no_lock():
    yield
