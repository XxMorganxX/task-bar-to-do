# todo_app.mcp_server

Local stdio MCP server that lets Claude Code (or any MCP client) file and read todos.

Todos created here land in the same Supabase table the overlay and menu bar app use.

This server:

- runs over **stdio**, spawned on demand by the client — no daemon, works with the menu bar app stopped
- exposes **only** todo tools
- is **read + create only** — it cannot complete or delete todos

## Tools

| Tool | Purpose |
|---|---|
| `create_todo` | File a todo. Requires a concise `title` and a detailed `description`. |
| `list_todos` | Read existing todos — check for duplicates, see what's due or overdue. |
| `list_categories` | The live list of categories available for filing. |

### Required shape of a todo

- **`title`** — concise, scannable label. Max 80 characters (`MAX_TITLE_LENGTH`).
- **`description`** — the detail that makes the todo actionable later, with no memory of the
  session that created it. Minimum 30 characters (`MIN_DESCRIPTION_LENGTH`).
- **`category`** — optional, and must already exist. Agents cannot invent categories: an
  unknown value is rejected with an error naming the valid choices. Omitting it produces an
  uncategorized todo, exactly like the overlay's default.
- **`due_at`** — optional. ISO 8601 or natural language ("tomorrow 5pm").

## Categories

Categories are owned by the app, not by this server. The list is the union of:

1. categories registered via the overlay (`POST /api/todos/categories`), including ones with
   no todos yet, and
2. groups already in use on existing todos.

Both are surfaced by `todo_app/todo_categories.py`, the single source of
truth, which persists to `state/todos/categories/<user>.json`.

To add a category, create it in the todo overlay UI. This server deliberately has no tool
for creating one.

**Removed categories.** Removing a folder in the overlay is visual only — it stops being
offered for new todos here and in the UI, but todos already filed under it keep their group
untouched and keep displaying it. Removed names are stored in the `hidden` list of the state
file and are excluded from `list_categories`, so `create_todo` refuses them. Re-creating a
category with the same name in the UI restores it.

**Schema caching caveat:** MCP clients cache tool schemas, so `create_todo`'s `category`
enum is a snapshot from server start. Validation at call time runs against the *live*
registry, so a category added mid-session is still accepted; it joins the enum next session.
`list_categories` always returns the current truth.

## Attribution

Todos are stamped `source_type: "claude_code"` with `source_metadata.created_via:
"claude_code_mcp"`, which:

- distinguishes them from overlay-created (`manual`) todos everywhere
- gives them their own cache file, `state/todos/<user>/claude_code_todos.json`
- includes them in the queued briefing digests via `TodoManager.TODO_BRIEFING_SOURCE_TYPES`

## Installation

Registered at user scope, so every Claude Code session on this machine can file todos
(the server name is up to you; tools appear as `mcp__<name>__create_todo` etc.):

```bash
claude mcp add todos -s user \
  -- /path/to/to-do_app/venv/bin/python -m todo_app.mcp_server
```

No `PYTHONPATH` needed: `todo_app` is installed into the venv (`pip install -e .`), so it
imports from whatever working directory Claude Code starts the session in.

Verify with `claude mcp get todos`; remove with `claude mcp remove todos -s user`.

## Configuration

`config.py` holds every tuneable value and every model-facing string (tool descriptions,
parameter descriptions, error messages). Nothing in `server.py` defines them inline, so the
server's behavior is auditable from one file.

## A note on stdout

On stdio transport, stdout **is** the JSON-RPC stream. A stray print from any
dependency would corrupt it, so `server.py` redirects stdout to
stderr around imports and every tool call, handing the transport the real stdout only when
it starts. Any new code path here must not print to stdout.

## Tests

```bash
./venv/bin/python -m pytest tests/test_todo_mcp_service.py tests/test_todo_categories.py -q
```
