"""Request-scoped anonymous identity for user-owned tool operations."""

from __future__ import annotations

from contextvars import ContextVar, Token


_current_user_id: ContextVar[str] = ContextVar("current_user_id", default="cli-local")


def set_current_user_id(user_id: str) -> Token[str]:
    return _current_user_id.set(user_id)


def reset_current_user_id(token: Token[str]) -> None:
    _current_user_id.reset(token)


def current_user_id() -> str:
    return _current_user_id.get()


get_current_user_id = current_user_id
