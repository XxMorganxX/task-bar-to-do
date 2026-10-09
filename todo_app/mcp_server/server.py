"""
Local stdio MCP server exposing the todo list to Claude Code sessions.

Runs on demand over stdio, needs no daemon, and exposes only todo tools. Writes go through
`TodoManager`, the same path the overlay uses, so todos created here are indistinguishable
from any other except by `source_type`.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

# On stdio transport, stdout IS the JSON-RPC stream: a single stray print corrupts it and
# the session dies. TodoManager's dependencies may print at import or at runtime, so stdout
# is redirected to stderr for
# everything except the transport itself (which captures the real stdout in main()).
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("todo_mcp")

_REAL_STDOUT = sys.stdout

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

with contextlib.redirect_stdout(sys.stderr):
    from fastmcp import FastMCP  # noqa: E402
    from pydantic import Field  # noqa: E402

    from todo_app.todo_categories import TodoCategoryRegistry  # noqa: E402
    from todo_app.todo_manager import TodoManager  # noqa: E402
    from todo_app.mcp_server import config  # noqa: E402


def _quiet():
    """Keep library stdout writes off the protocol stream."""
    return contextlib.redirect_stdout(sys.stderr)


class TodoService:
    """Todo operations backing the MCP tools, independent of the MCP layer."""

    def __init__(
        self,
        *,
        todo_manager: Optional[TodoManager] = None,
        category_registry: Optional[TodoCategoryRegistry] = None,
    ):
        self._todos = todo_manager or TodoManager()
        self._categories = category_registry or TodoCategoryRegistry()

    def is_available(self) -> bool:
        return self._todos.is_available()

    def default_user(self) -> str:
        return self._todos.normalize_user(None)

    def _groups_in_use(self, user: str) -> List[str]:
        """Category names already carried by this user's todos."""
        if not self._todos.is_available():
            return []
        try:
            todos = self._todos.list_todos(
                user=user,
                include_completed=True,
                limit=config.CATEGORY_SCAN_LIMIT,
            )
        except Exception as exc:
            logger.warning("Could not scan todos for categories: %s", exc)
            return []

        names = []
        for todo in todos:
            if str(todo.get("source_type") or "").lower() == "calendar":
                continue
            name = todo.get("group")
            if name:
                names.append(str(name))
        return names

    def list_categories(self, user: Optional[str] = None) -> List[str]:
        """Live category list: registered in the app, plus any already in use."""
        normalized_user = self._todos.normalize_user(user)
        return self._categories.list_categories(
            normalized_user,
            groups_in_use=self._groups_in_use(normalized_user),
        )

    def create_todo(
        self,
        *,
        title: str,
        description: str,
        category: Optional[str] = None,
        due_at: Optional[str] = None,
        user: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self._todos.is_available():
            raise RuntimeError(config.ERROR_SUPABASE_UNAVAILABLE)

        clean_title = (title or "").strip()
        if not clean_title:
            raise ValueError(config.ERROR_TITLE_REQUIRED)
        if len(clean_title) > config.MAX_TITLE_LENGTH:
            raise ValueError(config.ERROR_TITLE_TOO_LONG % len(clean_title))

        clean_description = (description or "").strip()
        if not clean_description:
            raise ValueError(config.ERROR_DESCRIPTION_REQUIRED)
        if len(clean_description) < config.MIN_DESCRIPTION_LENGTH:
            raise ValueError(config.ERROR_DESCRIPTION_TOO_SHORT % len(clean_description))
        clean_description = clean_description[: config.MAX_DESCRIPTION_LENGTH]

        normalized_user = self._todos.normalize_user(user)
        # Raises ValueError naming the valid choices if the category is unknown, which is
        # what prevents an agent from inventing categories.
        resolved_category = self._categories.resolve(
            normalized_user,
            category,
            groups_in_use=self._groups_in_use(normalized_user),
        )

        todo = self._todos.create_todo(
            user=normalized_user,
            title=clean_title,
            details=clean_description,
            due_at=due_at,
            source_type=config.SOURCE_TYPE,
            group=resolved_category,
            source_metadata={"created_via": config.CREATED_VIA},
        )

        return {
            "id": todo.get("id"),
            "title": todo.get("title"),
            "description": todo.get("details"),
            "category": resolved_category,
            "due_at": todo.get("due_at"),
            "due_display": todo.get("due_display"),
        }

    def list_todos(
        self,
        *,
        include_completed: bool = False,
        limit: int = config.DEFAULT_LIST_LIMIT,
        only_due_today: bool = False,
        only_overdue: bool = False,
        user: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self._todos.is_available():
            raise RuntimeError(config.ERROR_SUPABASE_UNAVAILABLE)

        bounded_limit = max(1, min(int(limit or config.DEFAULT_LIST_LIMIT), config.MAX_LIST_LIMIT))
        todos = self._todos.list_todos(
            user=self._todos.normalize_user(user),
            include_completed=include_completed,
            limit=bounded_limit,
            only_due_today=only_due_today,
            only_overdue=only_overdue,
        )

        return [
            {
                "id": todo.get("id"),
                "title": todo.get("title"),
                "description": todo.get("details"),
                "category": todo.get("group"),
                "due_at": todo.get("due_at"),
                "due_display": todo.get("due_display"),
                "completed": bool(todo.get("completed")),
                "source": todo.get("source_type"),
            }
            for todo in todos
        ]


def create_server(service: Optional[TodoService] = None) -> FastMCP:
    with _quiet():
        todo_service = service or TodoService()
    mcp = FastMCP(name=config.SERVER_NAME)

    # Snapshot of categories for the create_todo schema. MCP clients cache tool schemas, so
    # this list is fixed for the session while validation at call time runs against the
    # live registry -- a category added in the app mid-session is still accepted.
    try:
        with _quiet():
            known_categories = todo_service.list_categories()
    except Exception as exc:
        logger.warning("Could not load categories at startup: %s", exc)
        known_categories = []

    category_hint = ", ".join(known_categories) if known_categories else "(none defined yet)"

    @mcp.tool(name="create_todo", description=config.CREATE_TODO_DESCRIPTION)
    def create_todo(
        title: Annotated[
            str,
            Field(description=config.PARAM_TITLE, max_length=config.MAX_TITLE_LENGTH),
        ],
        description: Annotated[
            str,
            Field(
                description=config.PARAM_DESCRIPTION,
                min_length=config.MIN_DESCRIPTION_LENGTH,
            ),
        ],
        category: Annotated[Optional[str], Field(description=config.PARAM_CATEGORY)] = None,
        due_at: Annotated[Optional[str], Field(description=config.PARAM_DUE_AT)] = None,
        user: Annotated[Optional[str], Field(description=config.PARAM_USER)] = None,
    ) -> Dict[str, Any]:
        try:
            with _quiet():
                todo = todo_service.create_todo(
                    title=title,
                    description=description,
                    category=category,
                    due_at=due_at,
                    user=user,
                )
            return {"success": True, "todo": todo}
        except (ValueError, RuntimeError) as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("create_todo failed")
            return {"success": False, "error": f"Failed to create todo: {exc}"}

    @mcp.tool(name="list_todos", description=config.LIST_TODOS_DESCRIPTION)
    def list_todos(
        include_completed: Annotated[
            bool, Field(description=config.PARAM_INCLUDE_COMPLETED)
        ] = False,
        limit: Annotated[
            int,
            Field(description=config.PARAM_LIMIT, ge=1, le=config.MAX_LIST_LIMIT),
        ] = config.DEFAULT_LIST_LIMIT,
        only_due_today: Annotated[
            bool, Field(description=config.PARAM_ONLY_DUE_TODAY)
        ] = False,
        only_overdue: Annotated[bool, Field(description=config.PARAM_ONLY_OVERDUE)] = False,
        user: Annotated[Optional[str], Field(description=config.PARAM_USER)] = None,
    ) -> Dict[str, Any]:
        try:
            with _quiet():
                todos = todo_service.list_todos(
                    include_completed=include_completed,
                    limit=limit,
                    only_due_today=only_due_today,
                    only_overdue=only_overdue,
                    user=user,
                )
            return {"success": True, "count": len(todos), "todos": todos}
        except (ValueError, RuntimeError) as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("list_todos failed")
            return {"success": False, "error": f"Failed to list todos: {exc}"}

    @mcp.tool(name="list_categories", description=config.LIST_CATEGORIES_DESCRIPTION)
    def list_categories(
        user: Annotated[Optional[str], Field(description=config.PARAM_USER)] = None,
    ) -> Dict[str, Any]:
        try:
            with _quiet():
                categories = todo_service.list_categories(user)
            return {
                "success": True,
                "count": len(categories),
                "categories": categories,
                "note": (
                    "Categories are defined by the user in the todo app. "
                    "Use one of these exactly, or omit the category."
                ),
            }
        except Exception as exc:
            logger.exception("list_categories failed")
            return {"success": False, "error": f"Failed to list categories: {exc}"}

    # Annotate the create_todo schema with the categories known at startup so the model
    # sees valid choices without an extra tool call.
    _annotate_category_enum(mcp, known_categories, category_hint)

    return mcp


def _annotate_category_enum(mcp: FastMCP, categories: List[str], hint: str) -> None:
    """Inject the known categories into create_todo's input schema."""
    try:
        tool = mcp._tool_manager._tools.get("create_todo")
        schema = getattr(tool, "parameters", None)
        if not isinstance(schema, dict):
            return
        prop = schema.get("properties", {}).get("category")
        if not isinstance(prop, dict):
            return
        prop["description"] = f"{config.PARAM_CATEGORY} Currently defined: {hint}."
        if categories:
            prop["enum"] = [*categories, None]
    except Exception as exc:  # Schema internals are version-specific; never fail startup.
        logger.debug("Could not annotate category enum: %s", exc)


def main() -> None:
    server = create_server()
    # Hand the transport the untouched stdout it needs for JSON-RPC framing.
    sys.stdout = _REAL_STDOUT
    server.run("stdio", show_banner=False)


if __name__ == "__main__":
    main()
