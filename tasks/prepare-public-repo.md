# Prepare to-do_app for a public GitHub repo

## Goal

Make the repo safe and usable as a public project: no secrets, no personal data, no
machine-specific paths, and enough setup docs that someone else can run it.

## Audit (2026-10-08)

- Secrets: `.env`, `creds/`, `state/` already gitignored; repo has no commits, so no history to scrub.
- Personal data in tracked files:
  - `todo_app/settings.py` — hardcoded `PRIMARY_USER` and `CALENDAR_USERS` with real
    calendar emails / group-calendar IDs.
  - `todo_app/todo_manager.py` — `_map_calendar_user_to_assistant_user` hardcoded
    two specific first names.
  - `launchd/*.plist`, `todo`, `menubar/app.py` — a personal reverse-DNS label and
    notification names, absolute home-directory paths.
  - `todo_app/mcp_server/README.md` — absolute path.
  - Tests and docstrings use the user's name and employer as sample data.
- Missing for outsiders: Supabase schema (`todos` + `briefing_announcements`, both
  written by `TodoManager`), generic install docs, LICENSE.

## Decisions

- **Identity and calendars come from local config, not code.** `TODO_USER` in `.env`;
  calendars in a gitignored `calendars.json` (committed `calendars.example.json`).
  No calendars file → calendar linking simply has no targets.
- **Calendar→user mapping generalized**: match configured user names against the
  calendar key instead of hardcoded names. Same result for the current setup.
- **launchd plist and Daemon Deck manifest become templates** rendered by
  `todo install` from the repo's own location, so the repo works from any path. The
  manifest is only installed if `~/.config/background-systems/registry/` exists.
- **Label + notification names**: generic default `local.todo-app`, defined once in
  `settings.py`; the `todo` script reads them from there.
- **Ship `supabase/schema.sql`** for both tables (taken from HomeAssist's migrations +
  SETUP.md). Briefing generation stays as-is (fork compatibility); the table just has to exist.
- **Keep `tasks/` logs public** (default from global CLAUDE.md: commit them) — they hold
  design history, no secrets.
- Push needs explicit user confirmation (outward-facing).

## Progress log
- 2026-10-08 — TDD: `_map_calendar_user_to_assistant_user` now matches configured user
  names inside the calendar key (2 new tests, red → green). `get_default_calendar_user`
  returns None with no calendars instead of raising StopIteration (2 new tests).
- 2026-10-08 — `settings.py`: `TODO_USER`, `TODO_HOUSEHOLD_MEMBERS`, `TODO_OVERLAY_PORT`,
  `TODO_LAUNCHD_LABEL` from env; calendars from gitignored `calendars.json`. This
  machine's values moved to its `.env` / `calendars.json`, keeping the existing label so
  the installed agent didn't need re-registering. Service-account file renamed to
  `creds/google-service-account.json`.
- 2026-10-08 — plist + Daemon Deck manifest are now templates rendered by `todo install`
  from the repo's own path; the manifest is only written if the registry dir exists.
  Rendered plist diffed equal to the installed one.
- 2026-10-08 — Sample data in tests/docstrings: names → Alice, employer → Northwind
  ("AcmeCorp" broke an alphabetical-order assertion, so picked a name sorting after
  "HomeAssist"). Display/model-facing "HomeAssist Todos" → "Todos". Kept the
  `homeassist.todo.*` localStorage keys and the Obsidian `homeassist_*` markers: renaming
  them would reset saved UI state / orphan existing vault notes.
- 2026-10-08 — Added `supabase/schema.sql`; columns verified equal to the live tables.
  Rewrote README, `.env.example`, MCP README for outsiders.
- 2026-10-08 — Checks: 139 passed, also with Supabase pointed at an unreachable URL (no
  network in tests). No scanner installed, so scanned the 68 commit candidates for the
  actual values in `.env`, `creds/*.json`, `calendars.json` plus key patterns: only false
  positives (public Google OAuth URLs; the launchd label in the extraction log).
  Restarted the agent on the new code: running, 4 calendars loaded from local config.
- 2026-10-08 — Global git identity is a work account (`morgan@instalily.ai`); the GitHub
  CLI is logged in as a personal account. Asked the user which identity to commit as.
