"""Structured JSONL logging for LangChain tool executions."""

from __future__ import annotations

import ast
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import ToolMessage

from src.core.config import PROJECT_ROOT

logger = logging.getLogger("purchase_torob.tools")


class ToolCallLogger(BaseCallbackHandler):
    """Append one structured record for each completed tool invocation."""

    def __init__(self) -> None:
        self._started: dict[str, float] = {}
        self._calls: dict[str, dict[str, Any]] = {}
        self._log_path = Path(os.getenv("TOOL_LOG_PATH", "logs/tool-calls.jsonl"))
        if not self._log_path.is_absolute():
            self._log_path = PROJECT_ROOT / self._log_path

    def on_tool_start(self, serialized, input_str, *, run_id, **kwargs) -> None:
        call_id = str(run_id)
        self._started[call_id] = time.monotonic()
        self._calls[call_id] = {
            "at": datetime.now(timezone.utc).isoformat(),
            "name": (serialized or {}).get("name", "unknown"),
            "args": parse_log_value(input_str),
        }

    def on_tool_end(self, output, *, run_id, **kwargs) -> None:
        self._finish(run_id, output=output)

    def on_tool_error(self, error, *, run_id, **kwargs) -> None:
        self._finish(run_id, error=str(error))

    def _finish(self, run_id, *, output=None, error=None) -> None:
        call_id = str(run_id)
        entry = self._calls.pop(call_id, {"name": "unknown"})
        started = self._started.pop(call_id, time.monotonic())
        payload = _tool_payload(output.content) if isinstance(output, ToolMessage) else output
        entry.update(
            ok=error is None and getattr(output, "status", "success") != "error",
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        if error:
            entry["error"] = error
        if isinstance(payload, dict):
            entry["source"] = payload.get("source")
            data = payload.get("data")
            entry["result_count"] = len(data) if isinstance(data, list) else None
            entry["result_preview"] = str(data)[:500]
        elif output is not None:
            entry["result_preview"] = str(output)[:500]
        self._write(entry)

    def _write(self, entry: dict[str, Any]) -> None:
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError:
            logger.exception("Could not append tool-call log")


def parse_log_value(value: str) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value


def _tool_payload(content: Any) -> dict[str, Any] | None:
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
    if not isinstance(content, str):
        return None
    parsed = parse_log_value(content)
    return parsed if isinstance(parsed, dict) else None
