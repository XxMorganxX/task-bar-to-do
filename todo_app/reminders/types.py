"""Pure data types for the smart reminder system.

No I/O, no third-party imports — only stdlib. Every other module in the
package depends on these definitions; they never depend on anything else here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ReminderType(str, Enum):
    """How a todo should be reminded about. Inferred by the classifier."""

    HARD_DEADLINE = "hard_deadline"          # A: dated, ramp up to the deadline
    SCHEDULED_POINT = "scheduled_point"      # B: dated point-in-time event
    FLOATING_IMPORTANT = "floating_important"  # C: undated but high value
    LOW_EFFORT_ADMIN = "low_effort_admin"    # D: undated, trivial, surface once
    HABIT_ROUTINE = "habit_routine"          # E: recurring cadence


class LifecycleState(str, Enum):
    """Where a todo sits in the reminder lifecycle."""

    OPEN = "open"
    SEEN = "seen"
    REMINDED = "reminded"
    SNOOZED = "snoozed"
    WAITING_ON_SOMEONE = "waiting_on_someone"
    ABANDONED = "abandoned"
    DONE = "done"


class UserAction(str, Enum):
    """An action the user took in response to a reminder."""

    DONE = "done"
    SNOOZE = "snooze"
    DISMISS = "dismiss"
    SEEN = "seen"
    REMINDED = "reminded"


@dataclass(frozen=True)
class ClassifierResult:
    """Output of classifying a todo. ``importance`` is normalized 0..1."""

    reminder_type: ReminderType
    importance: float
    effort_minutes: int
    classifier: str
    confidence: float = 1.0


@dataclass(frozen=True)
class CandidateMoment:
    """A single moment a policy proposes surfacing a reminder."""

    when: datetime
    label: str
    policy_name: str


@dataclass(frozen=True)
class ScoredCandidate:
    """A candidate moment with its attention score and component breakdown."""

    candidate: CandidateMoment
    score: float
    components: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ReminderContext:
    """Snapshot of the world used to decide whether to interrupt now."""

    now: datetime
    hour: int
    day_of_week: int  # Monday=0 .. Sunday=6
    quiet_hours: bool = False
    calendar_state: str = "free"  # "free" | "busy"
    recent_interrupt_load: int = 0  # reminders sent in the recent window


@dataclass(frozen=True)
class ReminderDecision:
    """The engine's decision to surface a reminder for a todo right now."""

    todo: Dict[str, Any]
    scored: ScoredCandidate
    reminder_type: ReminderType
    reason: str
    channel: str


@dataclass(frozen=True)
class ReminderEvent:
    """A row destined for the ``reminder_events`` behavior log."""

    todo_id: str
    user_id: str
    reminded_at: datetime
    channel: str
    reminder_type: str
    user_action: Optional[str] = None
    snoozed_until: Optional[datetime] = None
    completed_within_minutes: Optional[int] = None
    score: Optional[float] = None
    reason: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


__all__ = [
    "ReminderType",
    "LifecycleState",
    "UserAction",
    "ClassifierResult",
    "CandidateMoment",
    "ScoredCandidate",
    "ReminderContext",
    "ReminderDecision",
    "ReminderEvent",
]
