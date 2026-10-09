"""Single source of truth for to-do_app paths, identity and integration config.

Loads the app's own `.env` on import, so every entry point (overlay, menu bar, MCP
server) sees the same environment without a shell wrapper sourcing it first.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

APP_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(APP_ROOT / ".env")

# -- Local filesystem ----------------------------------------------------------
STATE_ROOT = APP_ROOT / "state"
TODO_STATE_ROOT = STATE_ROOT / "todos"
CALENDAR_TODO_CACHE_PATH = STATE_ROOT / "calendar_todo_cache.json"
LOG_DIR = APP_ROOT / "logs"
CREDS_DIR = APP_ROOT / "creds"

# -- Overlay HTTP server (embedded in the menu bar app) ------------------------
OVERLAY_HOST = "127.0.0.1"
OVERLAY_PORT = int(os.environ.get("TODO_OVERLAY_PORT", "8421"))

# -- macOS integration ---------------------------------------------------------
# launchd label of the menu bar agent; also prefixes the distributed notifications
# the `todo show` launcher uses to toggle the panel of an already-running app.
LAUNCHD_LABEL = os.environ.get("TODO_LAUNCHD_LABEL", "local.todo-app")
MENUBAR_TOGGLE_NOTIFICATION = f"{LAUNCHD_LABEL}.toggle"
MENUBAR_SHOW_NOTIFICATION = f"{LAUNCHD_LABEL}.show"

# -- Identity ------------------------------------------------------------------
# Todos are stored per user_id; this is the user the UI and MCP server act as.
PRIMARY_USER = os.environ.get("TODO_USER", "User")
HOUSEHOLD_MEMBERS = [
    name.strip() for name in os.environ.get("TODO_HOUSEHOLD_MEMBERS", "").split(",") if name.strip()
]

# -- Google Calendar (optional: "link todo to calendar") -----------------------
DEBUG_MODE = False
DEFAULT_TIME_ZONE = os.environ.get("DEFAULT_TIME_ZONE", "America/New_York")
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_FILE", str(CREDS_DIR / "google-service-account.json")
)
# Calendars a todo can be linked to, keyed by "<user>_<name>". Personal data, so it lives
# in a gitignored file; see calendars.example.json. Missing file = no linkable calendars.
CALENDARS_PATH = APP_ROOT / "calendars.json"


def _load_calendar_users() -> dict:
    if not CALENDARS_PATH.exists():
        return {}
    return json.loads(CALENDARS_PATH.read_text(encoding="utf-8"))


CALENDAR_USERS = _load_calendar_users()
