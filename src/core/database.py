"""Small SQLite connection factory shared by repositories and data scripts."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator

from src.core.config import settings


@contextmanager
def database(*, readonly: bool = False) -> Iterator[sqlite3.Connection]:
    path = settings.database_path
    if not path.exists() and readonly:
        raise FileNotFoundError(f"فایل پایگاه داده پیدا نشد: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)

    target = f"file:{path}?mode=ro" if readonly else str(path)
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
