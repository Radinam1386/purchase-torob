"""Explicit user preference persistence in SQLite."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from langchain_core.tools import tool

from src.core.database import database
from src.core.tools.common import tool_result
from src.core.tools.schemas import LoadPreferencesInput, SavePreferenceInput


@tool(args_schema=SavePreferenceInput)
def save_user_preference(user_id: str, key: str, value: str) -> dict:
    """ذخیره‌ی ترجیح پایدار کاربر برای گفتگوهای بعدی."""
    with database() as connection:
        row = connection.execute(
            "SELECT preferences_json FROM user_preferences WHERE user_id = ?", (user_id,)
        ).fetchone()
        preferences = json.loads(row["preferences_json"]) if row else {}
        preferences[key] = value
        connection.execute(
            """
            INSERT INTO user_preferences(user_id, preferences_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                preferences_json = excluded.preferences_json,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                json.dumps(preferences, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    return tool_result("simulated", {"saved": True, "key": key})


@tool(args_schema=LoadPreferencesInput)
def load_user_preferences(user_id: str) -> dict:
    """خواندن ترجیحات ذخیره‌شده‌ی کاربر."""
    with database(readonly=True) as connection:
        row = connection.execute(
            "SELECT preferences_json FROM user_preferences WHERE user_id = ?", (user_id,)
        ).fetchone()
    preferences = json.loads(row["preferences_json"]) if row else {}
    return tool_result("simulated", preferences)
