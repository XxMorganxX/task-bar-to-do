"""User and calendar identity lookups, backed by `todo_app.settings`.

Same function names as HomeAssist's `mcp_server.user_config`, so the forked
`TodoManager` and overlay call them unchanged.
"""

from __future__ import annotations

from typing import List, Optional

from todo_app import settings


def get_primary_user() -> str:
    return settings.PRIMARY_USER


def get_available_users() -> List[str]:
    return [settings.PRIMARY_USER, *settings.HOUSEHOLD_MEMBERS]


def get_calendar_users() -> List[str]:
    return list(settings.CALENDAR_USERS.keys())


def get_default_calendar_user() -> Optional[str]:
    """First configured calendar, or None when calendar linking isn't set up."""
    return next(iter(settings.CALENDAR_USERS), None)


def get_notification_users() -> List[str]:
    return get_available_users()


def get_default_notification_user() -> str:
    return settings.PRIMARY_USER
