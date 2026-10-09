"""Reminder policies (A-E): map a classified todo to a policy and generate the
candidate moments that policy proposes. Pure functions — no I/O.

Dated policies (hard_deadline, scheduled_point) hang offsets off ``due_at``.
Undated policies (floating_important, low_effort_admin, habit_routine) hang a
cadence off the todo's creation time and last-reminded time.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from . import config
from .metadata import get_reminder_meta, parse_iso
from .types import CandidateMoment, ClassifierResult, ReminderType


def select_policy(classified: ClassifierResult, todo: Dict[str, Any]) -> Dict[str, Any]:
    """Pick the policy table for a todo.

    Honors the classifier's type, but falls back to a sensible dated/undated
    choice when the type and the todo's due-date status disagree.
    """

    has_due = parse_iso(todo.get("due_at")) is not None
    policy = config.POLICIES.get(classified.reminder_type.value)

    if policy is None:
        policy = config.POLICIES[ReminderType.FLOATING_IMPORTANT.value]

    # A dated policy on an undated todo can't ramp toward a deadline; fall back.
    if policy.get("dated") and not has_due:
        fallback = (
            ReminderType.LOW_EFFORT_ADMIN
            if classified.effort_minutes <= config.LOW_EFFORT_MAX_MINUTES
            else ReminderType.FLOATING_IMPORTANT
        )
        policy = config.POLICIES[fallback.value]

    return policy


def generate_candidate_moments(
    todo: Dict[str, Any],
    policy: Dict[str, Any],
    classified: ClassifierResult,
    now: datetime,
) -> List[CandidateMoment]:
    """Produce the moments a policy proposes, within the candidate horizon."""

    if policy.get("dated"):
        return _dated_moments(todo, policy, classified, now)
    return _undated_moments(todo, policy, classified, now)


def _dated_moments(
    todo: Dict[str, Any],
    policy: Dict[str, Any],
    classified: ClassifierResult,
    now: datetime,
) -> List[CandidateMoment]:
    due = parse_iso(todo.get("due_at"))
    if due is None:
        return []

    offsets = list(policy.get("offsets_before_due_minutes", []))
    if classified.effort_minutes <= config.LOW_EFFORT_MAX_MINUTES:
        trim = set(policy.get("low_effort_trim_offsets_minutes", []))
        offsets = [o for o in offsets if o not in trim]

    moments: List[CandidateMoment] = []
    name = policy["name"]
    for offset in offsets:
        when = due - timedelta(minutes=offset)
        moments.append(
            CandidateMoment(when=when, label=_offset_label(offset), policy_name=name)
        )

    if policy.get("morning_of"):
        morning = due.replace(
            hour=policy.get("morning_hour", 9), minute=0, second=0, microsecond=0
        )
        if morning < due:
            moments.append(
                CandidateMoment(when=morning, label="morning of", policy_name=name)
            )

    return sorted(moments, key=lambda m: m.when)


def _undated_moments(
    todo: Dict[str, Any],
    policy: Dict[str, Any],
    classified: ClassifierResult,
    now: datetime,
) -> List[CandidateMoment]:
    created = parse_iso(todo.get("created_at")) or now
    meta = get_reminder_meta(todo)
    last_reminded = parse_iso(meta.get("last_reminded_at"))
    reminder_count = int(meta.get("reminder_count", 0) or 0)
    deferral_count = int(meta.get("deferral_count", 0) or 0)

    max_reminders = policy.get("max_reminders")
    if max_reminders is not None and reminder_count >= max_reminders:
        return []

    name = policy["name"]
    horizon = now + timedelta(days=config.CANDIDATE_HORIZON_DAYS)

    if last_reminded is None:
        first = created + timedelta(hours=policy["first_nudge_after_hours"])
        return [CandidateMoment(when=first, label="first nudge", policy_name=name)]

    repeat_hours = policy["repeat_every_hours"]
    escalate_after = policy.get("escalate_after_deferrals")
    if escalate_after is not None and deferral_count >= escalate_after:
        repeat_hours = policy.get("escalation_repeat_every_hours", repeat_hours)

    nxt = last_reminded + timedelta(hours=repeat_hours)
    if nxt > horizon:
        return []
    label = "escalated nudge" if repeat_hours != policy["repeat_every_hours"] else "repeat nudge"
    return [CandidateMoment(when=nxt, label=label, policy_name=name)]


def _offset_label(offset_minutes: int) -> str:
    if offset_minutes >= config.DAY:
        days = offset_minutes // config.DAY
        return f"{days} day{'s' if days != 1 else ''} before due"
    if offset_minutes >= config.HOUR:
        hours = offset_minutes // config.HOUR
        return f"{hours} hour{'s' if hours != 1 else ''} before due"
    return f"{offset_minutes} minutes before due"


__all__ = ["select_policy", "generate_candidate_moments"]
