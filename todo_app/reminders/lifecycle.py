"""Lifecycle transitions for a todo's reminder state. Pure: takes the current
reminder-namespace metadata and a user action, returns the metadata updates to
merge (via ``TodoManager.update_todo_metadata``). Never does I/O.

States: open, seen, reminded, snoozed, waiting_on_someone, abandoned, done.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from . import config
from .types import LifecycleState, UserAction


def is_suppressed(metadata: Dict[str, Any]) -> bool:
    """True if the todo's lifecycle state should block all reminders."""

    state = metadata.get("lifecycle_state")
    return state in config.SUPPRESSED_STATES


def apply_transition(
    metadata: Dict[str, Any],
    action: UserAction,
    now: datetime,
    *,
    snooze_until: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return the reminder-metadata fields to merge after ``action``.

    Only the changed keys are returned; the caller merges them onto the existing
    ``source_metadata.reminders`` namespace.
    """

    reminder_count = int(metadata.get("reminder_count", 0) or 0)
    deferral_count = int(metadata.get("deferral_count", 0) or 0)
    updates: Dict[str, Any] = {}

    if action == UserAction.REMINDED:
        updates["lifecycle_state"] = LifecycleState.REMINDED.value
        updates["last_reminded_at"] = now.isoformat()
        updates["reminder_count"] = reminder_count + 1

    elif action == UserAction.SEEN:
        updates["lifecycle_state"] = LifecycleState.SEEN.value

    elif action == UserAction.DONE:
        updates["lifecycle_state"] = LifecycleState.DONE.value

    elif action == UserAction.SNOOZE:
        until = snooze_until or (now + timedelta(hours=config.DEFAULT_SNOOZE_HOURS))
        updates["lifecycle_state"] = LifecycleState.SNOOZED.value
        updates["snooze_until"] = until.isoformat()
        updates["deferral_count"] = deferral_count + 1

    elif action == UserAction.DISMISS:
        deferral_count += 1
        updates["deferral_count"] = deferral_count
        if deferral_count >= config.ABANDON_AFTER_DISMISSALS:
            updates["lifecycle_state"] = LifecycleState.ABANDONED.value
        else:
            updates["lifecycle_state"] = LifecycleState.SEEN.value

    else:  # pragma: no cover - exhaustive over UserAction
        raise ValueError(f"Unhandled action: {action}")

    return updates


__all__ = ["is_suppressed", "apply_transition"]
