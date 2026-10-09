"""Pure helpers for reading reminder state off a todo and parsing timestamps.

The reminder system stores its per-todo state under
``todo["source_metadata"]["reminders"]``. These helpers never mutate the todo;
writes go through ``TodoManager.update_todo_metadata`` (added in P2).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .config import METADATA_NAMESPACE


def _source_metadata(todo: Dict[str, Any]) -> Dict[str, Any]:
    raw = todo.get("source_metadata") or {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return dict(raw) if isinstance(raw, dict) else {}


def get_reminder_meta(todo: Dict[str, Any]) -> Dict[str, Any]:
    """Return the ``reminders`` namespace dict from a todo (empty if absent)."""

    meta = _source_metadata(todo).get(METADATA_NAMESPACE)
    return dict(meta) if isinstance(meta, dict) else {}


def parse_iso(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 string into a tz-aware UTC datetime, or None."""

    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


__all__ = ["get_reminder_meta", "parse_iso"]
