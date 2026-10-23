"""Small SQLite connection factory shared by repositories and data scripts."""

from __future__ import annotations

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


@contextmanager
def database_write_lock(database_path: Path, *, exclusive: bool = False):
    """Coordinate app writes with the loader's atomic database replacement."""
    lock_path = database_path.with_name(f"{database_path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def _no_lock():
    yield
