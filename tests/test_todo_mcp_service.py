import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from todo_app.todo_categories import TodoCategoryRegistry  # noqa: E402
from todo_app.mcp_server import config  # noqa: E402
from todo_app.mcp_server.server import TodoService  # noqa: E402


class FakeTodoManager:
    """Stands in for the Supabase-backed TodoManager."""

    def __init__(self, *, available=True, todos=None):
        self._available = available
        self._todos = todos or []
        self.created = []

    def is_available(self):
        return self._available

    def normalize_user(self, user):
        return user.title() if user else "Alice"

    def list_todos(self, *, user, include_completed=False, limit=25, **_kwargs):
        todos = self._todos if include_completed else [t for t in self._todos if not t.get("completed")]
        return todos[:limit]

    def create_todo(self, **kwargs):
        self.created.append(kwargs)
        return {
            "id": "todo_test_1",
            "title": kwargs["title"],
            "details": kwargs["details"],
            "due_at": kwargs.get("due_at"),
            "due_display": None,
            "group": kwargs.get("group"),
        }


@pytest.fixture
def service(tmp_path):
    manager = FakeTodoManager()
    registry = TodoCategoryRegistry(state_root=tmp_path)
    return TodoService(todo_manager=manager, category_registry=registry), manager, registry


def _valid_description():
    return "Enough detail to make this actionable a week from now."


# --- title and description validation ------------------------------------------------


def test_creating_a_todo_stores_the_description_as_details(service):
    svc, manager, _ = service

    svc.create_todo(title="Ship it", description=_valid_description())

    assert manager.created[0]["details"] == _valid_description()


def test_rejects_a_blank_title(service):
    svc, _, _ = service

    with pytest.raises(ValueError):
        svc.create_todo(title="   ", description=_valid_description())


def test_rejects_a_title_longer_than_the_limit(service):
    svc, _, _ = service

    with pytest.raises(ValueError, match="Title"):
        svc.create_todo(
            title="x" * (config.MAX_TITLE_LENGTH + 1),
            description=_valid_description(),
        )


def test_rejects_a_missing_description(service):
    svc, _, _ = service

    with pytest.raises(ValueError, match="description is required"):
        svc.create_todo(title="Ship it", description="")


def test_rejects_a_description_that_is_too_short(service):
    svc, _, _ = service

    with pytest.raises(ValueError, match="characters"):
        svc.create_todo(title="Ship it", description="too short")


def test_truncates_an_overlong_description(service):
    svc, manager, _ = service

    svc.create_todo(title="Ship it", description="y" * (config.MAX_DESCRIPTION_LENGTH + 500))

    assert len(manager.created[0]["details"]) == config.MAX_DESCRIPTION_LENGTH


# --- attribution ---------------------------------------------------------------------


def test_todos_are_attributed_to_claude_code(service):
    svc, manager, _ = service

    svc.create_todo(title="Ship it", description=_valid_description())

    assert manager.created[0]["source_type"] == config.SOURCE_TYPE
    assert manager.created[0]["source_metadata"]["created_via"] == config.CREATED_VIA


def test_claude_code_todos_reach_spoken_briefings():
    from todo_app.todo_manager import TodoManager

    assert config.SOURCE_TYPE in TodoManager.TODO_BRIEFING_SOURCE_TYPES


# --- categories ----------------------------------------------------------------------


def test_a_registered_category_is_accepted(service):
    svc, manager, registry = service
    registry.register("Alice", "HomeAssist")

    svc.create_todo(title="Ship it", description=_valid_description(), category="HomeAssist")

    assert manager.created[0]["group"] == "HomeAssist"


def test_a_category_is_matched_case_insensitively(service):
    svc, manager, registry = service
    registry.register("Alice", "Northwind")

    svc.create_todo(title="Ship it", description=_valid_description(), category="northwind")

    assert manager.created[0]["group"] == "Northwind"


def test_an_invented_category_is_rejected(service):
    svc, _, registry = service
    registry.register("Alice", "HomeAssist")

    with pytest.raises(ValueError, match="Unknown category"):
        svc.create_todo(
            title="Ship it",
            description=_valid_description(),
            category="Totally Made Up",
        )


def test_rejection_message_names_the_valid_categories(service):
    svc, _, registry = service
    registry.register("Alice", "HomeAssist")

    with pytest.raises(ValueError, match="HomeAssist"):
        svc.create_todo(
            title="Ship it",
            description=_valid_description(),
            category="Totally Made Up",
        )


def test_omitting_the_category_creates_an_uncategorized_todo(service):
    svc, manager, _ = service

    svc.create_todo(title="Ship it", description=_valid_description())

    assert manager.created[0]["group"] is None


def test_a_category_defined_after_startup_is_accepted(service):
    """Categories are validated against the live registry, not a startup snapshot."""
    svc, manager, registry = service

    registry.register("Alice", "Defined Later")
    svc.create_todo(title="Ship it", description=_valid_description(), category="Defined Later")

    assert manager.created[0]["group"] == "Defined Later"


def test_categories_include_groups_already_used_by_todos(tmp_path):
    manager = FakeTodoManager(todos=[{"title": "x", "group": "Northwind", "source_type": "manual"}])
    svc = TodoService(
        todo_manager=manager,
        category_registry=TodoCategoryRegistry(state_root=tmp_path),
    )

    assert svc.list_categories() == ["Northwind"]


def test_calendar_groups_are_excluded_from_categories(tmp_path):
    manager = FakeTodoManager(
        todos=[{"title": "x", "group": "Some Calendar", "source_type": "calendar"}]
    )
    svc = TodoService(
        todo_manager=manager,
        category_registry=TodoCategoryRegistry(state_root=tmp_path),
    )

    assert svc.list_categories() == []


# --- availability --------------------------------------------------------------------


def test_create_reports_a_clear_error_when_the_database_is_down(tmp_path):
    svc = TodoService(
        todo_manager=FakeTodoManager(available=False),
        category_registry=TodoCategoryRegistry(state_root=tmp_path),
    )

    with pytest.raises(RuntimeError, match="unavailable"):
        svc.create_todo(title="Ship it", description=_valid_description())


def test_list_reports_a_clear_error_when_the_database_is_down(tmp_path):
    svc = TodoService(
        todo_manager=FakeTodoManager(available=False),
        category_registry=TodoCategoryRegistry(state_root=tmp_path),
    )

    with pytest.raises(RuntimeError, match="unavailable"):
        svc.list_todos()


# --- listing -------------------------------------------------------------------------


def test_list_excludes_completed_todos_by_default(tmp_path):
    manager = FakeTodoManager(
        todos=[
            {"id": "1", "title": "open", "completed": False},
            {"id": "2", "title": "done", "completed": True},
        ]
    )
    svc = TodoService(
        todo_manager=manager,
        category_registry=TodoCategoryRegistry(state_root=tmp_path),
    )

    assert [todo["title"] for todo in svc.list_todos()] == ["open"]


def test_list_limit_is_capped_at_the_maximum(tmp_path):
    manager = FakeTodoManager(todos=[{"id": str(i), "title": str(i)} for i in range(200)])
    svc = TodoService(
        todo_manager=manager,
        category_registry=TodoCategoryRegistry(state_root=tmp_path),
    )

    assert len(svc.list_todos(limit=999)) == config.MAX_LIST_LIMIT


def test_list_exposes_details_as_description(tmp_path):
    manager = FakeTodoManager(todos=[{"id": "1", "title": "t", "details": "the detail"}])
    svc = TodoService(
        todo_manager=manager,
        category_registry=TodoCategoryRegistry(state_root=tmp_path),
    )

    assert svc.list_todos()[0]["description"] == "the detail"
