import importlib.util
import json
from pathlib import Path

import pytest


def _load_todo_categories_module():
    module_path = (
        Path(__file__).parent.parent / "todo_app" / "todo_categories.py"
    )
    spec = importlib.util.spec_from_file_location("todo_categories_test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def registry(tmp_path):
    module = _load_todo_categories_module()
    return module.TodoCategoryRegistry(state_root=tmp_path)


@pytest.fixture
def normalize():
    return _load_todo_categories_module().normalize_category_name


# --- normalization ------------------------------------------------------------------


def test_collapses_internal_whitespace(normalize):
    assert normalize("  Project    Phoenix ") == "Project Phoenix"


def test_returns_none_for_blank_input(normalize):
    assert normalize("   ") is None


def test_returns_none_for_missing_input(normalize):
    assert normalize(None) is None


def test_truncates_names_beyond_max_length(normalize):
    module = _load_todo_categories_module()

    normalized = normalize("x" * (module.MAX_CATEGORY_LENGTH + 25))

    assert len(normalized) == module.MAX_CATEGORY_LENGTH


# --- registration -------------------------------------------------------------------


def test_registered_category_is_listed(registry):
    registry.register("Alice", "HomeAssist")

    assert registry.list_categories("Alice") == ["HomeAssist"]


def test_registered_category_survives_a_new_registry_instance(registry, tmp_path):
    registry.register("Alice", "HomeAssist")

    module = _load_todo_categories_module()
    reloaded = module.TodoCategoryRegistry(state_root=tmp_path)

    assert reloaded.list_categories("Alice") == ["HomeAssist"]


def test_register_returns_the_normalized_name(registry):
    assert registry.register("Alice", "  Home   Assist ") == "Home Assist"


def test_register_rejects_a_blank_name(registry):
    with pytest.raises(ValueError):
        registry.register("Alice", "   ")


def test_reregistering_a_differently_cased_name_does_not_duplicate(registry):
    registry.register("Alice", "HomeAssist")
    registry.register("Alice", "homeassist")

    assert registry.list_categories("Alice") == ["HomeAssist"]


def test_categories_are_scoped_per_user(registry):
    registry.register("Alice", "HomeAssist")

    assert registry.list_categories("Alex") == []


def test_user_scoping_is_case_insensitive(registry):
    registry.register("Alice", "HomeAssist")

    assert registry.list_categories("alice") == ["HomeAssist"]


def test_unregister_removes_the_category(registry):
    registry.register("Alice", "HomeAssist")
    registry.unregister("Alice", "HomeAssist")

    assert registry.list_categories("Alice") == []


def test_unregister_matches_case_insensitively(registry):
    registry.register("Alice", "HomeAssist")

    assert registry.unregister("Alice", "homeassist") is True
    assert registry.list_categories("Alice") == []


def test_unregister_reports_false_when_absent(registry):
    assert registry.unregister("Alice", "Nonexistent") is False


# --- union with in-use groups -------------------------------------------------------


def test_groups_in_use_appear_without_being_registered(registry):
    categories = registry.list_categories("Alice", groups_in_use=["Northwind"])

    assert categories == ["Northwind"]


def test_registered_and_in_use_categories_are_merged(registry):
    registry.register("Alice", "HomeAssist")

    categories = registry.list_categories("Alice", groups_in_use=["Northwind"])

    assert categories == ["HomeAssist", "Northwind"]


def test_a_category_both_registered_and_in_use_appears_once(registry):
    registry.register("Alice", "Northwind")

    categories = registry.list_categories("Alice", groups_in_use=["northwind"])

    assert categories == ["Northwind"]


def test_registered_spelling_wins_over_in_use_casing(registry):
    registry.register("Alice", "Northwind")

    categories = registry.list_categories("Alice", groups_in_use=["northwind"])

    assert categories == ["Northwind"]


def test_blank_groups_in_use_are_ignored(registry):
    categories = registry.list_categories("Alice", groups_in_use=["", None, "  "])

    assert categories == []


def test_categories_are_sorted_case_insensitively(registry):
    registry.register("Alice", "zebra")
    registry.register("Alice", "Apple")

    assert registry.list_categories("Alice") == ["Apple", "zebra"]


# --- hiding (the "delete category" action: visual only, never touches past todos) ----


def test_hiding_removes_a_registered_category_from_the_list(registry):
    registry.register("Alice", "HomeAssist")

    registry.hide("Alice", "HomeAssist")

    assert registry.list_categories("Alice") == []


def test_hiding_removes_a_category_that_is_still_used_by_past_todos(registry):
    """The whole point: a category in use must still disappear from the pickers."""
    registry.hide("Alice", "Northwind")

    assert registry.list_categories("Alice", groups_in_use=["Northwind"]) == []


def test_hiding_matches_case_insensitively(registry):
    registry.register("Alice", "Northwind")

    registry.hide("Alice", "northwind")

    assert registry.list_categories("Alice") == []


def test_hiding_leaves_other_categories_alone(registry):
    registry.register("Alice", "HomeAssist")
    registry.register("Alice", "Northwind")

    registry.hide("Alice", "HomeAssist")

    assert registry.list_categories("Alice") == ["Northwind"]


def test_hidden_categories_survive_a_new_registry_instance(registry, tmp_path):
    registry.hide("Alice", "Northwind")

    module = _load_todo_categories_module()
    reloaded = module.TodoCategoryRegistry(state_root=tmp_path)

    assert reloaded.list_categories("Alice", groups_in_use=["Northwind"]) == []


def test_hiding_is_scoped_per_user(registry):
    registry.hide("Alice", "Northwind")

    assert registry.list_categories("Alex", groups_in_use=["Northwind"]) == ["Northwind"]


def test_hide_rejects_a_blank_name(registry):
    with pytest.raises(ValueError):
        registry.hide("Alice", "  ")


def test_recreating_a_hidden_category_brings_it_back(registry):
    registry.hide("Alice", "HomeAssist")

    registry.register("Alice", "HomeAssist")

    assert registry.list_categories("Alice") == ["HomeAssist"]


def test_recreating_a_hidden_category_matches_case_insensitively(registry):
    registry.hide("Alice", "Northwind")

    registry.register("Alice", "northwind")

    assert registry.list_categories("Alice", groups_in_use=["Northwind"]) == ["northwind"]


def test_unhide_restores_a_category_that_is_still_in_use(registry):
    registry.hide("Alice", "Northwind")

    assert registry.unhide("Alice", "Northwind") is True
    assert registry.list_categories("Alice", groups_in_use=["Northwind"]) == ["Northwind"]


def test_unhide_reports_false_when_not_hidden(registry):
    assert registry.unhide("Alice", "Northwind") is False


def test_hidden_categories_are_listed_for_inspection(registry):
    registry.hide("Alice", "Northwind")

    assert registry.list_hidden("Alice") == ["Northwind"]


def test_a_hidden_category_cannot_be_used_for_new_todos(registry):
    registry.hide("Alice", "Northwind")

    with pytest.raises(ValueError):
        registry.resolve("Alice", "Northwind", groups_in_use=["Northwind"])


# --- resolution (what the MCP uses to validate a requested category) ----------------


def test_resolve_returns_the_canonical_spelling(registry):
    registry.register("Alice", "HomeAssist")

    assert registry.resolve("Alice", "homeassist") == "HomeAssist"


def test_resolve_returns_none_for_no_category(registry):
    assert registry.resolve("Alice", None) is None


def test_resolve_rejects_an_unknown_category(registry):
    registry.register("Alice", "HomeAssist")

    with pytest.raises(ValueError) as excinfo:
        registry.resolve("Alice", "Made Up")

    assert "HomeAssist" in str(excinfo.value)


def test_resolve_accepts_a_category_only_present_in_use(registry):
    assert registry.resolve("Alice", "northwind", groups_in_use=["Northwind"]) == "Northwind"


# --- persistence format -------------------------------------------------------------


def test_state_file_is_human_readable_json(registry, tmp_path):
    registry.register("Alice", "HomeAssist")

    state_file = tmp_path / "categories" / "alice.json"
    payload = json.loads(state_file.read_text(encoding="utf-8"))

    assert payload["categories"] == ["HomeAssist"]
    assert payload["user_id"] == "Alice"


def test_corrupt_state_file_is_treated_as_empty(registry, tmp_path):
    state_file = tmp_path / "categories" / "alice.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{not valid json", encoding="utf-8")

    assert registry.list_categories("Alice") == []


def test_register_recovers_from_a_corrupt_state_file(registry, tmp_path):
    state_file = tmp_path / "categories" / "alice.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{not valid json", encoding="utf-8")

    registry.register("Alice", "HomeAssist")

    assert registry.list_categories("Alice") == ["HomeAssist"]
