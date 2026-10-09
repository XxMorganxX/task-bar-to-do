"""
Single source of truth for every tuneable value and every model-facing string in the
Claude Code todo MCP server. Nothing in server.py should define a description or a
parameter inline.
"""

# =============================================================================
# PARAMETERS
# =============================================================================

SERVER_NAME = "Todos"

# Attribution stamped on every todo this server creates. Distinguishes Claude-created
# todos from overlay-created ones (`manual`) everywhere in the system, and gets its own
# cache file via TodoManager.refresh_todo_cache_files.
SOURCE_TYPE = "claude_code"
CREATED_VIA = "claude_code_mcp"

# A title is a scannable label in the overlay, not a description.
MAX_TITLE_LENGTH = 80

# A description this short is not a description. Enforced so todos filed by an agent
# carry enough context to be actionable days later, without the original session.
MIN_DESCRIPTION_LENGTH = 30
MAX_DESCRIPTION_LENGTH = 4000

# Read limits.
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100

# Bound the todo scan used to discover which categories are in use.
CATEGORY_SCAN_LIMIT = 500


# =============================================================================
# TOOL DESCRIPTIONS
# =============================================================================

CREATE_TODO_DESCRIPTION = """Add a todo to the user's real todo list.

These todos appear in the user's desktop overlay and menu bar app. Treat them as real
commitments, not scratch notes.

Use this when the user asks you to remember, track, or follow up on something, or when
work surfaces that they clearly need to do later but not now.

Do NOT use this for your own intermediate task tracking during a session.

Every todo needs:
- `title`: a concise, scannable label (like a good commit subject). Max %(max_title)d characters.
- `description`: the detail that makes the todo actionable later, when neither you nor the
  user remembers this session. State what needs doing, why it came up, and any specifics
  (file paths, names, links, decisions already made). Minimum %(min_desc)d characters.
- `category` (optional): must be one the user already defined. Call `list_categories` if
  unsure. Never invent one; omit it instead and the todo is filed as uncategorized.
- `due_at` (optional): only when the user states or clearly implies a deadline. Accepts
  ISO 8601 or natural language such as "tomorrow 5pm" or "next friday".
""" % {
    "max_title": MAX_TITLE_LENGTH,
    "min_desc": MIN_DESCRIPTION_LENGTH,
}

LIST_TODOS_DESCRIPTION = """List the user's existing todos.

Use this before creating a todo to avoid filing a duplicate, and whenever the user asks
what is on their list, what is overdue, or what is due today.

Returns open todos by default, newest-relevant first.
"""

LIST_CATEGORIES_DESCRIPTION = """List the categories available for filing todos.

Categories are defined by the user in the todo app; this server cannot create
them. Returns the live list, so it reflects categories added since this session started.

Call this when unsure which category fits, before using `create_todo`. If none fit, omit
the category rather than inventing one.
"""


# =============================================================================
# PARAMETER DESCRIPTIONS
# =============================================================================

PARAM_TITLE = "Concise, scannable label for the todo. Max %d characters." % MAX_TITLE_LENGTH

PARAM_DESCRIPTION = (
    "Detailed context that makes this todo actionable later, without access to this "
    "session: what needs doing, why it came up, and relevant specifics such as file paths, "
    "names, or decisions already made. Minimum %d characters." % MIN_DESCRIPTION_LENGTH
)

PARAM_CATEGORY = (
    "Category to file the todo under. Must be one the user has already defined -- call "
    "list_categories to see them. Omit if none fit; the todo is then uncategorized."
)

PARAM_DUE_AT = (
    "Optional due time. ISO 8601 or natural language ('tomorrow 5pm', 'next friday 9am'). "
    "Only set this when the user stated or clearly implied a deadline."
)

PARAM_USER = "Target user. Defaults to the configured user (TODO_USER); normally omitted."

PARAM_INCLUDE_COMPLETED = "Include completed todos in the results."

PARAM_LIMIT = "Maximum number of todos to return (1-%d)." % MAX_LIST_LIMIT

PARAM_ONLY_DUE_TODAY = "Return only incomplete todos due today."

PARAM_ONLY_OVERDUE = "Return only incomplete todos that are past due."


# =============================================================================
# MESSAGES
# =============================================================================

ERROR_SUPABASE_UNAVAILABLE = (
    "The todo database is unavailable, so the todo was not saved. Check that "
    "SUPABASE_URL and SUPABASE_KEY are set in the app's .env file."
)

ERROR_TITLE_REQUIRED = "A title is required."

ERROR_TITLE_TOO_LONG = (
    "Title is %%d characters; keep it under %d. Move the detail into `description`."
    % MAX_TITLE_LENGTH
)

ERROR_DESCRIPTION_REQUIRED = (
    "A description is required. Explain what needs doing and why it came up, so the todo "
    "is actionable later."
)

ERROR_DESCRIPTION_TOO_SHORT = (
    "Description is only %%d characters; at least %d are required. Add enough context that "
    "this todo makes sense days from now." % MIN_DESCRIPTION_LENGTH
)
