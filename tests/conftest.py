"""Shared fixtures for to-do_app tests."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

APP_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(APP_ROOT))


@pytest.fixture
def mock_user_config_testuser():
    """Pin user/calendar identity so tests don't depend on settings.PRIMARY_USER."""
    with patch("todo_app.user_config.get_primary_user", return_value="TestUser"), \
         patch("todo_app.user_config.get_available_users", return_value=["TestUser", "Roommate"]), \
         patch("todo_app.user_config.get_default_calendar_user", return_value="testuser_personal"), \
         patch("todo_app.user_config.get_calendar_users", return_value=["testuser_personal", "testuser_school"]), \
         patch("todo_app.user_config.get_notification_users", return_value=["TestUser", "Roommate"]), \
         patch("todo_app.user_config.get_default_notification_user", return_value="TestUser"):
        yield
