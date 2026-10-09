# task-bar-to-do

A macOS todo app with three front ends over one Supabase table:

- **Menu bar app**: a native status-bar icon that toggles a floating todo panel.
- **Browser overlay**: the same UI and a JSON API on `http://127.0.0.1:8421`, served by the menu bar app.
- **MCP server**: a stdio [MCP](https://modelcontextprotocol.io) server so Claude Code (or any MCP client) can list todos and file new ones.

Optional extras: mirror todos into an Obsidian vault as notes, enrich those notes with
AI-extracted people/projects and related-todo links, and link a todo to a Google Calendar event.

It started life inside a private home-assistant project and was split out on its own; see
[tasks/](tasks/) for how that went.

## Requirements

- macOS (the menu bar app uses AppKit/WebKit via PyObjC; the overlay and MCP server are plain Python)
- Python 3.13
- A [Supabase](https://supabase.com) project

## Setup

```bash
git clone https://github.com/XxMorganxX/task-bar-to-do.git && cd task-bar-to-do
python3.13 -m venv venv
./venv/bin/pip install -r requirements.txt -e .
cp .env.example .env          # fill in SUPABASE_URL, SUPABASE_KEY, TODO_USER
./todo test                   # run the test suite
```

Create the tables: open the Supabase SQL Editor and run [`supabase/schema.sql`](supabase/schema.sql).

> `SUPABASE_KEY` grants read/write access to every row in `todos`. Keep `.env` local; it is gitignored.

Keep the clone out of iCloud-synced folders (Desktop, Documents): iCloud can evict files from
them, which breaks a venv in confusing ways.

## Run

```bash
./todo install     # install + start a per-user launchd agent (starts at login, restarts on crash)
./todo show        # toggle the floating panel
./todo open        # open the browser overlay
./todo status | logs | restart | stop | uninstall
```

`install` renders [`launchd/todo-app.plist.template`](launchd/) into
`~/Library/LaunchAgents/<label>.plist` (label: `TODO_LAUNCHD_LABEL`, default `local.todo-app`).
Logs go to `~/Library/Logs/todo-app/menubar.log`.

To run without launchd: `./venv/bin/python -m todo_app.menubar --show`, or just the web
server: `./venv/bin/python -m todo_app.overlay`.

### Claude Code (MCP)

```bash
claude mcp add todos -s user -- "$PWD/venv/bin/python" -m todo_app.mcp_server
```

Tools: `create_todo`, `list_todos`, `list_categories`. The server can read and create but never
complete or delete. Details: [todo_app/mcp_server/README.md](todo_app/mcp_server/README.md).

## Configuration

Everything is in `.env` (see [`.env.example`](.env.example)) and read in one place,
[`todo_app/settings.py`](todo_app/settings.py).

| Feature | How to enable |
|---|---|
| Obsidian export | `OBSIDIAN_EXPORT_ENABLED=true`, `OBSIDIAN_VAULT_PATH=/path/to/vault` |
| AI note enrichment | `TODO_GRAPH_ENRICHMENT_ENABLED=true` + `OPENAI_API_KEY` |
| Google Calendar linking | `cp calendars.example.json calendars.json`, list your calendars, and put a service-account JSON at `creds/google-service-account.json` (share each calendar with the service account). Inviting attendees needs user OAuth: `creds/google_creds_<user>.json`. |

`calendars.json`, `creds/` and `state/` are gitignored. They hold personal data.

### The `briefing_announcements` table

After every change, the app queues "todo digest" rows (what's due, what's overdue) into
`briefing_announcements` for a voice assistant or chat bot to deliver. Nothing in this repo
reads them; the table only has to exist.

## Layout

| Path | What |
|---|---|
| `todo_app/settings.py` | All paths, ports, identity, calendars; loads `.env` |
| `todo_app/todo_manager.py` | Supabase-backed todo core: CRUD, date parsing, caches, briefing digests |
| `todo_app/todo_categories.py` | User-defined categories (`state/todos/categories/`) |
| `todo_app/overlay/` | HTTP server, JSON API and web UI |
| `todo_app/menubar/` | Menu bar app; embeds the overlay server |
| `todo_app/mcp_server/` | stdio MCP server |
| `todo_app/reminders/` | Read-only reminder-schedule summary shown in the UI |
| `todo_app/obsidian/`, `todo_app/todo_graph/` | Obsidian export and AI enrichment |
| `todo_app/calendar_client.py` | Google Calendar client |
| `supabase/schema.sql` | Database schema |
| `launchd/` | launchd plist and registry-manifest templates used by `./todo install` |

## Development

```bash
./todo test        # or: ./venv/bin/python -m pytest -q
```

Tests don't touch the network or Supabase.

## License

[MIT](LICENSE)
