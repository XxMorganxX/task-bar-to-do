# Extract HomeAssist Todos into a standalone app

## Goal

Move the HomeAssist to-do app (overlay, menu bar, Claude Code MCP server, desktop launcher)
out of `~/Desktop/HomeAssistV3` into this self-contained package, first at
`~/Desktop/to-do_app`, now at `~/Development/to-do_app` (see 2026-10-08 move entry).
The app must run with no imports from, paths into, or processes owned by HomeAssist.

## Decisions (from the user, 2026-10-08)

- **Boundary: fork, no API.** to-do_app gets its own copy of the todo core
  (`TodoManager`, categories, the reminder-summary subset, Obsidian export, todo graph).
  HomeAssist keeps its copy for the voice tools, calendar sync and Discord bot. No HTTP
  API between them.
- **Data: same Supabase tables.** Nothing migrates. Both apps read/write the same rows.

## Decisions (mine, recorded for review)

- **Package name `todo_app`.** The folder is `to-do_app` (the user's name), but a hyphen
  can't be a Python identifier. Entry points: `python -m todo_app.overlay`,
  `todo_app.menubar`, `todo_app.mcp_server`.
- **Copy, don't redesign.** Modules are copied verbatim; only import paths, filesystem
  paths and config lookups change. Keeps the fork diffable against HomeAssist.
- **Data-compatibility strings stay identical**: `source_metadata.created_via =
  "todo_overlay"`, Obsidian markers (`homeassist_managed`, `homeassist:end`, ...),
  `source_type` values. Both copies write the same rows and the same vault notes, so
  they must agree on these.
- **One config module, `todo_app/settings.py`.** Loads `.env`, and holds every path,
  the user identity (was `state_management/app_state.json`) and `CALENDAR_USERS`
  (was `mcp_server/config.py`). Replaces `mcp_server.user_config` and is what the
  calendar client reads as `config`.
- **Google Calendar linking kept.** `calendar_client.py` copied; creds copied into the
  app's gitignored `creds/`.
- **Local state seeded, then independent.** `discord_bot/state/todos/` (category
  registry, per-source caches, graph embeddings) is copied into `state/todos/`. After
  cutover the two category registries diverge — accepted cost of the fork.
- **iCloud-safe layout** (superseded by the move to `~/Development`). Desktop is iCloud-synced and HomeAssist was hit by eviction
  (see HomeAssistV3 `tasks/icloud-eviction-recovery.md`). `venv`, `logs`, `state` are
  symlinks to `*.nosync` dirs, as in HomeAssist.
- **Lifecycle: own launchd agent** `local.todo-app`, running the menu bar
  app (it embeds the overlay HTTP server on 8421). Starts at login, restarts on crash.
  Registered in the local background-systems registry. Replaces HomeAssist's `homeassist run` starting the UI.
- **Own venv** (Python 3.13, same pinned versions HomeAssist uses).

## Approach

1. Scaffold package, settings, launcher, gitignore, requirements, venv.
2. Copy modules + todo tests, rewrite imports/paths. Tests green (baseline in
   HomeAssist: 123 passed across the 7 todo test files).
3. Verify isolation: grep for `assistant_framework|mcp_server|discord_bot|HomeAssistV3`.
4. Cutover: stop HomeAssist's todo UI, load the new agent, repoint Claude MCP config and
   `~/Desktop/HomeAssist Todos.app`, register manifest.
5. Remove `todo_overlay/`, `todo_menubar/`, `todo_mcp/`, the `todo-ui` command and the
   run-time UI startup from HomeAssist (uncommitted, for the user to review).

## Progress log

- 2026-10-08 — Mapped coupling. Core closure: `todo_manager`, `todo_categories`,
  `reminders/{summary,classification_cache,classifier,lifecycle,metadata,policies,config,types}`,
  `obsidian/`, `todo_graph/`, `providers/embedding` + `interfaces/embedding`,
  `mcp_server/user_config`, `mcp_server/clients/calendar_client`. Found
  `discord_bot/state/calendar_todo_cache.json` is read by the overlay but written by
  nothing (stale since May); pointed at app state, behavior unchanged (empty).
- 2026-10-08 — Copied modules into `todo_app/`, rewrote imports. Added `settings.py`
  (single config) and `user_config.py` (same function names as HomeAssist's). Calendar
  client now reads `todo_app.settings` as its `config` and `creds/` under the app.
- 2026-10-08 — Tests: 135 passed, the same 135 the 6 copied files run in HomeAssist
  (left out `test_reminders_core.py`; it covers engine/scoring/reason, which the app
  doesn't ship — only `summary` and its closure).
- 2026-10-08 — Running `python -m todo_app.overlay` from outside the folder failed
  (`No module named todo_app`). Added `pyproject.toml` + editable install so entry
  points and the MCP config need no PYTHONPATH.
- 2026-10-08 — Smoke tests against live Supabase: overlay on test port 8431 returned the
  identical open-todo set as HomeAssist's 8421 (6 ids, same hash); MCP stdio
  `initialize` → `tools/list` → `list_categories` OK. Imported all 40 modules: zero
  modules loaded from HomeAssistV3.
- 2026-10-08 — Found HomeAssist's graph embeddings at
  `assistant_framework/discord_bot/state/todos/...` — its `todo_graph/config.py` uses
  `parents[2]`, one level short. Seeded from there. The fork uses `settings` so it's moot.
- 2026-10-08 — Renamed menu bar distributed notifications
  `com.homeassist.todos.{toggle,show}` → `local.todo-app.*` so a stray
  HomeAssist menubar could never answer the app's launcher.
- 2026-10-08 — launchd logs go to `~/Library/Logs/todo-app/`, not the Desktop:
  `com.homeassist.mcp` (stderr under `~/Desktop`) sits at exit 78 EX_CONFIG, consistent
  with launchd being denied the TCC-protected Desktop.
- 2026-10-08 — Repointed Claude Code's user-scope `homeassist-todos` MCP server to
  `venv/bin/python -m todo_app.mcp_server` (name kept so `mcp__homeassist-todos__*`
  tool names and any allowlists keep working). `claude mcp get` → Connected.
- 2026-10-08 — `~/Desktop/HomeAssist Todos.app` now runs `to-do_app/todo show`.
- 2026-10-08 — HomeAssist `homeassist` script: removed the todo UI helpers, the
  `todo-ui` command (now prints a pointer here), the status lines, and the
  start/stop in `run`. Written to a new file and `mv`'d over so the live
  `homeassist run` (bash reads scripts lazily) keeps its old inode. Uncommitted.
  Caveat: that live process still has the old Ctrl+C trap, which kills whatever holds
  port 8421; launchd's KeepAlive restarts the app if so.
- 2026-10-08 — `todo install` (launchd bootstrap) was blocked by the auto-mode
  classifier as persistence; left for the user to run.
- 2026-10-08 — Deferred deleting `todo_overlay/`, `todo_menubar/`, `todo_mcp/` and
  `tests/test_todo_mcp_service.py` from HomeAssist: `todo_mcp/` is untracked and the
  others have uncommitted edits, so deleting discards work git can't restore. Waiting
  on the user's OK. HomeAssist doc mentions (SETUP.md, DEV_README.md) go with it.

- 2026-10-08 — User ran the old-UI `pkill` + `todo install`. Agent running (pid 14697),
  holding 8421, panel loaded data from Supabase, old `todo_overlay`/`todo_menubar`
  processes gone. TCC was not an issue: launchd's Python reads `~/Desktop/to-do_app` fine
  (logs are outside the Desktop). The background-systems registry shows `todo-app` as running.

- 2026-10-08 — Moved to `~/Development/to-do_app` at the user's request. Development
  isn't iCloud-synced, so dropped the `*.nosync` symlinks (`venv`, `logs`, `state` are
  plain dirs). A venv can't be relocated, so it was recreated + `pip install -e .`;
  135 passed. Repointed the plist, manifest `source`, the Desktop `.app` shortcut, the
  Claude MCP config (Connected), and HomeAssist's `todo-ui` pointer message. Reinstalled
  the agent: running from the new venv, 8421 healthy, the background-systems registry shows `todo-app running`.

- 2026-10-08 — User approved deletion. Removed from HomeAssistV3: `todo_overlay/`,
  `todo_menubar/`, `todo_mcp/`, `tests/test_todo_mcp_service.py`, the stale
  `.todo_{overlay,menubar}*.pid` files (incl. iCloud ` 2`..` 5` duplicates), and a
  malformed `.gitignore` line that had `todo_overlay/...` glued onto another entry.
  SETUP.md / DEV_README.md "Todo UI" sections now point here. HomeAssist's remaining todo
  tests: 102 passed; `discord_bot.bot`, `mcp_server.tools.{todos,calendar}` import fine.
  Four old `python -m todo_mcp` processes left running: they belong to Claude Code
  sessions started before the MCP repoint and exit with those sessions. Nothing committed.

## Open questions


## Out of scope

- HomeAssist's own todo core, voice tools, Discord bot — untouched (fork).
- Fixing `homeassist-mcp` launchd failure.
