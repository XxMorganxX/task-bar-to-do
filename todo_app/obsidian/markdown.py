"""Pure rendering: a todo dict -> an Obsidian note.

All machinery lives in YAML frontmatter; the body carries only distinctive content
(a `# title` heading and the todo's real context). No templated blocks, no Dataview
inline lines, no shared task-line boilerplate — identical template text across notes
poisons the KB's similarity clustering, so there is deliberately none of it here.

No IO in this module. The exporter owns files and cross-note link resolution; this
module owns the bytes that go in them.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from . import config

_DEFAULT_TZ = ZoneInfo(config.DEFAULT_TIMEZONE)


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------

def todo_group(todo: Mapping[str, Any]) -> Optional[str]:
    direct = todo.get("group")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    metadata = todo.get("source_metadata") or {}
    if isinstance(metadata, Mapping):
        value = metadata.get("todo_group")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def wikilink_name(name: str) -> str:
    """A filesystem- and wikilink-safe display name for a project/person link.

    Preserves spaces and case (so `[[Project Phoenix]]` reads naturally);
    only strips characters that are illegal in filenames or break wikilinks.
    """
    safe = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", name).strip()
    safe = re.sub(r"\s+", " ", safe)
    return safe or "Untitled"


def _local_date(iso_value: Any, tz) -> Optional[str]:
    if not iso_value:
        return None
    text = str(iso_value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(tz).date().isoformat()


def slugify(text: str, max_len: int = config.FILENAME_MAX_SLUG_LEN) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("-")
    return cleaned or "untitled"


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

def _yaml_scalar(value: str) -> str:
    """Quote a YAML string only when needed; escape embedded quotes."""
    if value == "" or re.search(r'[:#\[\]{},&*?|<>=!%@`"\']', value) or value != value.strip():
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def _wikilink_scalar(name: str) -> str:
    """A quoted YAML wikilink value, e.g. ``"[[Project Phoenix]]"``."""
    return '"[[' + name.replace('"', "") + ']]"'


def _frontmatter(todo: Mapping[str, Any], links: Mapping[str, Any], *, tz) -> str:
    lines = [
        f"{config.DOC_KIND_KEY}: {config.DOC_KIND_TODO}",
        f"{config.MANAGED_FLAG_KEY}: true",
        f"id: {_yaml_scalar(str(todo.get('id') or ''))}",
        f"status: {'done' if todo.get('completed') else 'open'}",
    ]

    project = links.get(config.FM_PROJECT)
    if project:
        lines.append(f"{config.FM_PROJECT}: {_wikilink_scalar(project)}")

    people = links.get(config.FM_PEOPLE) or []
    if people:
        rendered = ", ".join(_wikilink_scalar(p) for p in people)
        lines.append(f"{config.FM_PEOPLE}: [{rendered}]")

    related = links.get(config.FM_RELATED) or []
    if related:
        rendered = ", ".join(_wikilink_scalar(r) for r in related)
        lines.append(f"{config.FM_RELATED}: [{rendered}]")

    previous = links.get(config.FM_PREVIOUS)
    if previous:
        lines.append(f"{config.FM_PREVIOUS}: {_wikilink_scalar(previous)}")
    nxt = links.get(config.FM_NEXT)
    if nxt:
        lines.append(f"{config.FM_NEXT}: {_wikilink_scalar(nxt)}")

    due_date = _local_date(todo.get("due_at"), tz)
    if due_date:
        lines.append(f"due: {due_date}")

    lines.append(f"created: {_yaml_scalar(str(todo.get('created_at') or ''))}")
    lines.append(f"updated: {_yaml_scalar(str(todo.get('updated_at') or ''))}")

    if todo.get("completed") and todo.get("completed_at"):
        lines.append(f"completed_at: {_yaml_scalar(str(todo.get('completed_at')))}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# User-content preservation
# ---------------------------------------------------------------------------

def _preserved_tail(existing_text: Optional[str]) -> str:
    """User content lives after the boundary marker; carry it across re-exports.

    Falls back to the legacy managed-block end marker so notes written by the prior
    (templated-block) version migrate cleanly — their user tail is preserved.
    """
    if not existing_text:
        return ""
    for marker in (config.USER_CONTENT_MARKER, config.MANAGED_BLOCK_END):
        at = existing_text.rfind(marker)
        if at != -1:
            return existing_text[at + len(marker):].lstrip("\n")
    return ""


# ---------------------------------------------------------------------------
# Document assembly
# ---------------------------------------------------------------------------

def render_todo_document(
    todo: Mapping[str, Any],
    *,
    existing_text: Optional[str] = None,
    tz=_DEFAULT_TZ,
    links: Optional[Mapping[str, Any]] = None,
) -> str:
    """Render the full note: frontmatter machinery + a clean body.

    `links` holds the pre-resolved cross-note connections the exporter computed
    (``project``, ``people``, ``related``, ``previous``, ``next``) — each rendered
    as a frontmatter wikilink. Everything above the user-content marker is managed
    and regenerated each export; any user content after the marker in `existing_text`
    is preserved.
    """
    links = links or {}
    title = str(todo.get("title") or "").strip() or "Untitled"

    body_lines = [f"# {title}"]
    details = todo.get("details")
    if isinstance(details, str) and details.strip():
        body_lines.append("")
        body_lines.append(details.strip())

    document = (
        "---\n"
        + _frontmatter(todo, links, tz=tz)
        + "\n---\n"
        + "\n".join(body_lines)
        + "\n\n"
        + config.USER_CONTENT_MARKER
        + "\n"
    )

    tail = _preserved_tail(existing_text)
    if tail:
        return document + "\n" + tail
    return document
