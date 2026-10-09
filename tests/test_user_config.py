from unittest.mock import patch

from todo_app import user_config


def test_default_calendar_user_is_first_configured_calendar():
    calendars = {"alice_work": {}, "alice_personal": {}}
    with patch.object(user_config.settings, "CALENDAR_USERS", calendars):
        assert user_config.get_default_calendar_user() == "alice_work"


def test_default_calendar_user_is_none_when_no_calendars_configured():
    with patch.object(user_config.settings, "CALENDAR_USERS", {}):
        assert user_config.get_default_calendar_user() is None
