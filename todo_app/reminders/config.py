"""Single source of truth for the reminder system: every tunable value, every
policy table, and every prompt string. Nothing elsewhere in the package should
define a threshold, weight, cadence, or prompt inline.
"""

from __future__ import annotations

from typing import Any, Dict

from .types import ReminderType

# ---------------------------------------------------------------------------
# Metadata namespace (lives under todo.source_metadata.reminders.*)
# ---------------------------------------------------------------------------
METADATA_NAMESPACE = "reminders"

# ---------------------------------------------------------------------------
# Rolling engine
# ---------------------------------------------------------------------------
REMINDER_TICK_SECONDS = 15 * 60          # how often the engine evaluates open todos
CANDIDATE_WINDOW_MINUTES = 20            # a candidate moment fires if within +/- this of now
MAX_REMINDERS_PER_TICK = 2               # best-N surfaced per evaluation pass
MAX_INTERRUPTS_PER_WINDOW = 3            # interrupt budget over the recent window
RECENT_INTERRUPT_WINDOW_HOURS = 6        # window used to measure interrupt load

# A reminder for the same todo is throttled if reminded more recently than this.
MIN_HOURS_BETWEEN_REMINDERS = 3.0

# ---------------------------------------------------------------------------
# Quiet hours (local time). No reminders fire inside this window.
# ---------------------------------------------------------------------------
QUIET_HOURS_START = 22  # 10pm
QUIET_HOURS_END = 8     # 8am

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
# A candidate must score above this to be eligible to surface.
SCORE_THRESHOLD = 1.0

SCORE_WEIGHTS: Dict[str, float] = {
    "importance": 2.0,
    "urgency": 1.0,
    "deadline_pressure": 1.5,
    "staleness": 0.5,
    "effort": 0.5,
    "recent_reminder_penalty": 2.0,
    "bad_context_penalty": 1.5,
}

# Effort normalization: minutes mapped onto 0..1. A 5-minute task ~ 0.04,
# an all-day (>= this) task saturates at 1.0.
EFFORT_SATURATION_MINUTES = 480  # 8h

# Staleness saturates: a todo untouched this many days contributes the full term.
STALENESS_SATURATION_DAYS = 14.0

# Deadline pressure = clamp(PRESSURE_REF_HOURS / hours_until_due, 0, 1).
# At PRESSURE_REF_HOURS until due the term is ~1.0; further out it decays.
DEADLINE_PRESSURE_REF_HOURS = 3.0

# Below this many minutes a dated task is "low effort" and early ramp offsets
# are trimmed (a 5-minute form does not need a 7-day-out nudge).
LOW_EFFORT_MAX_MINUTES = 30

# ---------------------------------------------------------------------------
# Policy tables (A-E). Offsets are minutes BEFORE due for dated policies, and
# cadence definitions relative to creation/last-touch for undated policies.
# ---------------------------------------------------------------------------
DAY = 1440
HOUR = 60

POLICIES: Dict[str, Dict[str, Any]] = {
    ReminderType.HARD_DEADLINE.value: {
        "name": "hard_deadline",
        "dated": True,
        # T-7d, T-3d, T-1d, T-3h, T-30m
        "offsets_before_due_minutes": [7 * DAY, 3 * DAY, 1 * DAY, 3 * HOUR, 30],
        "morning_of": True,
        "morning_hour": 9,
        # For low-effort dated tasks, drop these far-out offsets.
        "low_effort_trim_offsets_minutes": [7 * DAY, 3 * DAY],
    },
    ReminderType.SCHEDULED_POINT.value: {
        "name": "scheduled_point",
        "dated": True,
        # T-24h, T-2h, T-15m
        "offsets_before_due_minutes": [24 * HOUR, 2 * HOUR, 15],
        "morning_of": False,
        "morning_hour": 9,
        "low_effort_trim_offsets_minutes": [],
    },
    ReminderType.FLOATING_IMPORTANT.value: {
        "name": "floating_important",
        "dated": False,
        "first_nudge_after_hours": 36,        # midpoint of 24-48h
        "repeat_every_hours": 96,             # ~every 4 days while untouched
        "escalate_after_deferrals": 3,
        "escalation_repeat_every_hours": 48,  # nag faster once escalated
    },
    ReminderType.LOW_EFFORT_ADMIN.value: {
        "name": "low_effort_admin",
        "dated": False,
        "first_nudge_after_hours": 2,
        "repeat_every_hours": 48,
        "max_reminders": 3,
    },
    ReminderType.HABIT_ROUTINE.value: {
        "name": "habit_routine",
        "dated": False,
        "first_nudge_after_hours": 24,
        "repeat_every_hours": 24,   # fixed daily cadence in v1
        "cadence_hour": 9,
    },
}

# How far ahead generate_candidate_moments looks for undated repeats.
CANDIDATE_HORIZON_DAYS = 14

# ---------------------------------------------------------------------------
# Lifecycle: states that suppress reminders entirely.
# ---------------------------------------------------------------------------
SUPPRESSED_STATES = ("waiting_on_someone", "abandoned", "done")

# After this many dismissals a floating/admin todo is marked abandoned.
ABANDON_AFTER_DISMISSALS = 4

# Default snooze if the user does not specify one.
DEFAULT_SNOOZE_HOURS = 3.0

# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------
DEFAULT_CHANNEL = "discord"

# ---------------------------------------------------------------------------
# Classifier — model config + prompt. See classifier.py (P2).
# Primary is OpenAI; Gemini is the fallback; the keyword heuristic is the last
# resort. The prompt strings are provider-agnostic.
# ---------------------------------------------------------------------------
CLASSIFIER_MODEL = "gpt-5-mini"                  # OpenAI primary (needs OPENAI_API_KEY)
CLASSIFIER_FALLBACK_MODEL = "gemini-2.0-flash"   # Gemini fallback (needs GEMINI_API_KEY)
CLASSIFIER_TEMPERATURE = 0.3

CLASSIFIER_SYSTEM_PROMPT = (
    "You classify personal todo items into a reminder strategy. Given a todo's "
    "title, optional details, and whether it has a due date, return JSON with: "
    "reminder_type (one of: hard_deadline, scheduled_point, floating_important, "
    "low_effort_admin, habit_routine), importance (0.0-1.0, how much it matters "
    "to the user's goals), and effort_minutes (estimated minutes to complete). "
    "Guidance: hard_deadline = dated task with real consequences if missed; "
    "scheduled_point = a dated appointment/event to show up to; "
    "floating_important = undated but high value; low_effort_admin = undated, "
    "trivial, quick; habit_routine = recurring habit. Respond with JSON only."
)

CLASSIFIER_USER_PROMPT_TEMPLATE = (
    "Title: {title}\nDetails: {details}\nHas due date: {has_due}\n"
    "Due at: {due_at}\n\nReturn the classification JSON."
)


__all__ = [
    "METADATA_NAMESPACE",
    "REMINDER_TICK_SECONDS",
    "CANDIDATE_WINDOW_MINUTES",
    "MAX_REMINDERS_PER_TICK",
    "MAX_INTERRUPTS_PER_WINDOW",
    "RECENT_INTERRUPT_WINDOW_HOURS",
    "MIN_HOURS_BETWEEN_REMINDERS",
    "QUIET_HOURS_START",
    "QUIET_HOURS_END",
    "SCORE_THRESHOLD",
    "SCORE_WEIGHTS",
    "EFFORT_SATURATION_MINUTES",
    "STALENESS_SATURATION_DAYS",
    "DEADLINE_PRESSURE_REF_HOURS",
    "LOW_EFFORT_MAX_MINUTES",
    "POLICIES",
    "CANDIDATE_HORIZON_DAYS",
    "SUPPRESSED_STATES",
    "ABANDON_AFTER_DISMISSALS",
    "DEFAULT_SNOOZE_HOURS",
    "DEFAULT_CHANNEL",
    "CLASSIFIER_MODEL",
    "CLASSIFIER_FALLBACK_MODEL",
    "CLASSIFIER_TEMPERATURE",
    "CLASSIFIER_SYSTEM_PROMPT",
    "CLASSIFIER_USER_PROMPT_TEMPLATE",
]
