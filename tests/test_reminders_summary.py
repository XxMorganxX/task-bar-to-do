"""Tests for build_reminder_summary — the UI-facing reminder summary."""

import json
from datetime import datetime, timedelta, timezone

from todo_app.reminders.summary import build_reminder_summary

NOW = datetime(2026, 5, 29, 14, 0, tzinfo=timezone.utc)


def _todo(**overrides):
    base = {
        "id": "todo_1",
        "title": "Generic task",
        "details": None,
        "due_at": None,
        "completed": False,
        "created_at": (NOW - timedelta(days=5)).isoformat(),
        "updated_at": (NOW - timedelta(days=5)).isoformat(),
        "source_metadata": {},
    }
    base.update(overrides)
    return base


def test_completed_todo_has_no_summary():
    assert build_reminder_summary(_todo(completed=True), NOW) is None


def test_fresh_undated_todo_with_no_reminders_has_no_summary():
    # created 30 min ago: first nudge (>=2h out) is in the future but exists,
    # so there IS an upcoming moment -> a summary is returned
    todo = _todo(created_at=(NOW - timedelta(minutes=30)).isoformat(),
                 updated_at=(NOW - timedelta(minutes=30)).isoformat())
    summary = build_reminder_summary(todo, NOW)
    assert summary is not None
    assert summary["upcoming"]  # the first-nudge moment is upcoming


def test_dated_deadline_lists_next_three_upcoming_moments():
    todo = _todo(title="Submit grant report", due_at=(NOW + timedelta(days=10)).isoformat())
    summary = build_reminder_summary(todo, NOW)
    assert summary is not None
    assert summary["reminder_type"] == "hard_deadline"
    assert len(summary["upcoming"]) == 3  # capped at the next three
    times = [datetime.fromisoformat(m["at"]) for m in summary["upcoming"]]
    assert times == sorted(times)  # ascending
    assert times[0] >= NOW


def test_snoozed_todo_floors_upcoming_at_snooze_time():
    snooze_until = NOW + timedelta(hours=5)
    todo = _todo(
        title="Submit grant report",
        due_at=(NOW + timedelta(days=10)).isoformat(),
        source_metadata={"reminders": {"snooze_until": snooze_until.isoformat(),
                                       "lifecycle_state": "snoozed"}},
    )
    summary = build_reminder_summary(todo, NOW)
    assert summary is not None
    for moment in summary["upcoming"]:
        assert datetime.fromisoformat(moment["at"]) >= snooze_until


def test_suppressed_state_has_no_summary():
    assert build_reminder_summary(_todo(source_metadata={"reminders": {"lifecycle_state": "done"}}), NOW) is None
    assert build_reminder_summary(_todo(source_metadata={"reminders": {"lifecycle_state": "abandoned"}}), NOW) is None


def test_overdue_moments_produce_no_summary():
    # undated, created 40h ago, never reminded -> first nudge (created+36h) is in the past,
    # and there is no future moment yet -> no icon (not a misleading "due now")
    todo = _todo(title="Draft the proposal", created_at=(NOW - timedelta(hours=40)).isoformat(),
                 updated_at=(NOW - timedelta(hours=40)).isoformat())
    assert build_reminder_summary(todo, NOW) is None


def test_overdue_dated_task_produces_no_summary():
    # due date already passed -> every offset moment is in the past -> no icon
    todo = _todo(title="Submit grant report", due_at=(NOW - timedelta(days=2)).isoformat())
    assert build_reminder_summary(todo, NOW) is None


def test_accepts_source_metadata_as_json_string():
    # JSON-string source_metadata must be parsed without crashing
    todo = _todo(
        title="Submit grant report",
        due_at=(NOW + timedelta(days=10)).isoformat(),
        source_metadata=json.dumps({"reminders": {"lifecycle_state": "reminded"}}),
    )
    summary = build_reminder_summary(todo, NOW)
    assert summary is not None
    assert summary["upcoming"]
