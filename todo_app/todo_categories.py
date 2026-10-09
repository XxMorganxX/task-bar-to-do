"""
Server-side registry of todo categories.

A category is the user-facing name for what `TodoManager` stores as a todo's *group*
(`source_metadata.todo_group`). Groups have always been free-form strings, which meant a
category only existed once some todo carried it, and categories created in the overlay UI
lived in browser `localStorage` — invisible to the menubar, to Supabase, and to any MCP
client, and lost whenever browser data was cleared.

This registry makes the set of categories real server-side state, so every surface
(overlay, menubar, MCP) reads one list. The list is the union of:

  1. categories explicitly registered here — including brand-new ones with no todos yet, and
  2. groups already in use on existing todos, which are passed in by the caller.

The registry deliberately does not talk to Supabase. Callers own todo retrieval and hand in
the groups already in use, which keeps this module independently testable and usable when
Supabase is unavailable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from todo_app import settings
from typing import Any, Dict, Iterable, List, Optional

# Category names share `TodoManager`'s group-name limit; see MAX_TODO_GROUP_LENGTH.
MAX_CATEGORY_LENGTH = 80

DEFAULT_STATE_ROOT = settings.TODO_STATE_ROOT


def normalize_category_name(name: Optional[str]) -> Optional[str]:
    """Canonical form of a category/group name, or None if it is effectively empty.

    This is the single definition of category normalization; `TodoManager` delegates its
    group normalization here so the two can never drift apart.
    """
    if name is None:
        return None
    normalized = re.sub(r"\s+", " ", str(name)).strip()
    if not normalized:
        return None
    if len(normalized) > MAX_CATEGORY_LENGTH:
        normalized = normalized[:MAX_CATEGORY_LENGTH].rstrip()
    return normalized or None


def _user_slug(user: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (user or "").strip().lower())
    return slug.strip("_") or "unknown"


class TodoCategoryRegistry:
    """Persists the set of categories a user has defined."""

    def __init__(self, *, state_root: Optional[Path] = None):
        # State lives in a `categories/` subdirectory rather than the per-user todo cache
        # directory: TodoManager.refresh_todo_cache_files deletes any unexpected .json in
        # that directory, which would silently destroy this file.
        self._state_dir = Path(state_root or DEFAULT_STATE_ROOT) / "categories"

    def _state_file(self, user: str) -> Path:
        return self._state_dir / f"{_user_slug(user)}.json"

    def _read_state(self, user: str) -> Dict[str, Any]:
        path = self._state_file(user)
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            # A corrupt or unreadable file must not take down the overlay or the MCP
            # server; treat it as empty and let the next write heal it.
            return {}
        return payload if isinstance(payload, dict) else {}

    def _names_at(self, user: str, key: str) -> List[str]:
        raw = self._read_state(user).get(key)
        if not isinstance(raw, list):
            return []
        return _dedupe_preserving_first(normalize_category_name(item) for item in raw)

    def _registered(self, user: str) -> List[str]:
        return self._names_at(user, "categories")

    def _hidden(self, user: str) -> List[str]:
        return self._names_at(user, "hidden")

    def _write(
        self,
        user: str,
        categories: List[str],
        hidden: Optional[List[str]] = None,
    ) -> None:
        path = self._state_file(user)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "user_id": user,
            "categories": _sorted_case_insensitively(categories),
            "hidden": _sorted_case_insensitively(
                self._hidden(user) if hidden is None else hidden
            ),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list_categories(
        self,
        user: str,
        *,
        groups_in_use: Optional[Iterable[Optional[str]]] = None,
    ) -> List[str]:
        """All categories for a user: registered ones plus any group already in use.

        Registered spellings take precedence, so a category registered as "Northwind" is
        not shadowed by a todo that happens to store it as "northwind".
        """
        combined = list(self._registered(user))
        combined.extend(groups_in_use or [])
        merged = _dedupe_preserving_first(normalize_category_name(item) for item in combined)
        hidden = {item.lower() for item in self._hidden(user)}
        return _sorted_case_insensitively(
            item for item in merged if item.lower() not in hidden
        )

    def list_hidden(self, user: str) -> List[str]:
        """Categories the user has removed from the pickers."""
        return _sorted_case_insensitively(self._hidden(user))

    def register(self, user: str, name: str) -> str:
        """Add a category and return its normalized name.

        Re-creating a previously hidden category un-hides it.
        """
        normalized = normalize_category_name(name)
        if not normalized:
            raise ValueError("Category name cannot be empty.")

        existing = self._registered(user)
        if not any(item.lower() == normalized.lower() for item in existing):
            existing.append(normalized)

        remaining_hidden = [
            item for item in self._hidden(user) if item.lower() != normalized.lower()
        ]
        self._write(user, existing, remaining_hidden)
        return normalized

    def hide(self, user: str, name: str) -> str:
        """Remove a category from the pickers without touching any todo.

        This is what "delete category" means here: the name stops being offered for new
        todos, in the overlay and to MCP clients alike. Todos already filed under it keep
        their group value untouched and keep displaying it, so history is never rewritten.
        Unlike `unregister`, this also suppresses a category that todos still use --
        otherwise deleting an in-use category would appear to do nothing.
        """
        normalized = normalize_category_name(name)
        if not normalized:
            raise ValueError("Category name cannot be empty.")

        remaining = [
            item for item in self._registered(user) if item.lower() != normalized.lower()
        ]
        hidden = self._hidden(user)
        if not any(item.lower() == normalized.lower() for item in hidden):
            hidden.append(normalized)

        self._write(user, remaining, hidden)
        return normalized

    def unhide(self, user: str, name: str) -> bool:
        """Restore a hidden category. Returns False if it was not hidden."""
        normalized = normalize_category_name(name)
        if not normalized:
            return False

        hidden = self._hidden(user)
        remaining = [item for item in hidden if item.lower() != normalized.lower()]
        if len(remaining) == len(hidden):
            return False

        self._write(user, self._registered(user), remaining)
        return True

    def unregister(self, user: str, name: str) -> bool:
        """Remove a category. Returns False if it was not registered.

        Todos already filed under the category keep it — it simply stops being offered as a
        choice, and reappears in `list_categories` for as long as any todo still uses it.
        """
        normalized = normalize_category_name(name)
        if not normalized:
            return False

        existing = self._registered(user)
        remaining = [item for item in existing if item.lower() != normalized.lower()]
        if len(remaining) == len(existing):
            return False

        self._write(user, remaining)
        return True

    def resolve(
        self,
        user: str,
        name: Optional[str],
        *,
        groups_in_use: Optional[Iterable[Optional[str]]] = None,
    ) -> Optional[str]:
        """Map a requested category to its canonical spelling, rejecting unknown ones.

        Returns None when no category was requested. Raises ValueError naming the valid
        choices otherwise — this is what stops an MCP client from inventing categories.
        """
        normalized = normalize_category_name(name)
        if not normalized:
            return None

        known = self.list_categories(user, groups_in_use=groups_in_use)
        for candidate in known:
            if candidate.lower() == normalized.lower():
                return candidate

        choices = ", ".join(known) if known else "(none defined yet)"
        raise ValueError(
            f"Unknown category '{normalized}'. Valid categories: {choices}. "
            "Create the category in the todo app first, or omit it."
        )


def _dedupe_preserving_first(names: Iterable[Optional[str]]) -> List[str]:
    seen: Dict[str, str] = {}
    for name in names:
        if not name:
            continue
        key = name.lower()
        if key not in seen:
            seen[key] = name
    return list(seen.values())


def _sorted_case_insensitively(names: Iterable[str]) -> List[str]:
    return sorted(names, key=lambda item: item.lower())
