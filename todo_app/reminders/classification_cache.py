"""Caching layer for classification results, stored on the todo's reminder
metadata. A todo is re-classified only when its classification-relevant inputs
(title, details, due-date presence) change — detected via an input hash.

Pure helpers: building the hash, deciding staleness, serializing a result to
metadata, and reconstructing a result from cached metadata. The actual write
goes through ``TodoManager.update_todo_metadata``; the read is done here.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, Optional

from .metadata import get_reminder_meta
from .types import ClassifierResult, ReminderType


def classification_input_hash(todo: Dict[str, Any]) -> str:
    """Stable hash of the inputs the classifier reads."""

    title = (todo.get("title") or "").strip().lower()
    details = (todo.get("details") or "").strip().lower()
    has_due = "1" if todo.get("due_at") else "0"
    payload = f"{title}\x1f{details}\x1f{has_due}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def is_classification_stale(todo: Dict[str, Any]) -> bool:
    """True if the todo has no cached classification or its inputs changed."""

    meta = get_reminder_meta(todo)
    cached_hash = meta.get("classified_input_hash")
    if not cached_hash or "type" not in meta:
        return True
    return cached_hash != classification_input_hash(todo)


def cached_result(todo: Dict[str, Any]) -> Optional[ClassifierResult]:
    """Reconstruct a ClassifierResult from cached metadata, or None."""

    meta = get_reminder_meta(todo)
    raw_type = meta.get("type")
    if raw_type is None:
        return None
    try:
        reminder_type = ReminderType(raw_type)
    except ValueError:
        return None
    return ClassifierResult(
        reminder_type=reminder_type,
        importance=float(meta.get("importance", 0.5)),
        effort_minutes=int(meta.get("effort_minutes", 30)),
        classifier=str(meta.get("classifier", "cache")),
    )


def cache_payload(
    result: ClassifierResult, todo: Dict[str, Any], now: datetime
) -> Dict[str, Any]:
    """Metadata fields (under the reminders namespace) to persist a result."""

    return {
        "type": result.reminder_type.value,
        "importance": result.importance,
        "effort_minutes": result.effort_minutes,
        "classifier": result.classifier,
        "classified_input_hash": classification_input_hash(todo),
        "classified_at": now.isoformat(),
    }


__all__ = [
    "classification_input_hash",
    "is_classification_stale",
    "cached_result",
    "cache_payload",
]
