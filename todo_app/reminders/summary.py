"""A read-only summary of a todo's reminder schedule + history, for surfacing in
UIs (e.g. the todo overlay's info icon).

Reuses the same policy logic the engine uses, so the times shown match what would
actually fire. Pure and cheap: no I/O and no network — it reads the cached
classification when present and otherwise falls back to the dependency-free
``HeuristicClassifier`` (never the LLM), so it is safe to call per-todo on every
UI refresh.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

from .classification_cache import cached_result, is_classification_stale
from .classifier import Classifier, HeuristicClassifier
from .lifecycle import is_suppressed
from .metadata import get_reminder_meta, parse_iso
from .policies import generate_candidate_moments, select_policy

MAX_UPCOMING = 3


def _normalized(todo: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of ``todo`` whose ``source_metadata`` is a dict (it can
    arrive as a JSON string from some callers)."""

    metadata = todo.get("source_metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    norm = dict(todo)
    norm["source_metadata"] = metadata
    return norm


def build_reminder_summary(
    todo: Dict[str, Any],
    now: datetime,
    classifier: Optional[Classifier] = None,
) -> Optional[Dict[str, Any]]:
    """Summarize a todo's reminders, or ``None`` when there is nothing to show.

    The returned dict carries only the upcoming (still-in-the-future) reminders:
        reminder_type, upcoming[{at, label}] (next MAX_UPCOMING)

    Past-due moments are never shown — an overdue task has no *next* reminder, so
    it gets no icon rather than a misleading "due now".
    """

    if todo.get("completed"):
        return None

    norm = _normalized(todo)
    meta = get_reminder_meta(norm)

    # Suppressed states (done/abandoned/waiting_on_someone) generate no upcoming
    # reminders, so there is nothing to show.
    if is_suppressed(meta):
        return None

    classified = cached_result(norm) if not is_classification_stale(norm) else None
    if classified is None:
        classified = (classifier or HeuristicClassifier()).classify(norm)

    policy = select_policy(classified, norm)
    moments = generate_candidate_moments(norm, policy, classified, now)

    # While snoozed, the next real reminder cannot fire before snooze_until.
    snooze_dt = parse_iso(meta.get("snooze_until"))
    floor = snooze_dt if (snooze_dt is not None and snooze_dt > now) else now

    upcoming = sorted((m for m in moments if m.when >= floor), key=lambda m: m.when)
    if not upcoming:
        return None

    return {
        "reminder_type": classified.reminder_type.value,
        "upcoming": [{"at": m.when.isoformat(), "label": m.label} for m in upcoming[:MAX_UPCOMING]],
    }


__all__ = ["build_reminder_summary"]
