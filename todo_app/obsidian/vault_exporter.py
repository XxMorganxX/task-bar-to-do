"""Concrete TodoExporter that writes one markdown note per todo into an Obsidian vault.

Reconciliation is keyed on the todo `id` (carried in frontmatter), not the filename,
so a title change updates the note in place — preserving the filename and its
backlinks — rather than orphaning it. Only notes carrying the managed flag are ever
touched.

Connections between notes are frontmatter wikilinks (Obsidian builds no semantic
links): each todo links to its ``project`` and, for chained todos, to its
``previous``/``next`` step, plus AI-enrichment ``people``/``related`` links. Cross-note
resolution (id -> note name) happens here, in a first planning pass.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from . import config, markdown
from .interface import ExportResult, TodoExporter

logger = logging.getLogger(__name__)


class ObsidianVaultExporter(TodoExporter):
    def __init__(
        self,
        *,
        vault_path,
        todos_subdir: str = config.DEFAULT_TODOS_SUBDIR,
        tz=None,
    ) -> None:
        self._vault_path = Path(vault_path)
        self._todos_dir = self._vault_path / todos_subdir
        self._open_dir = self._todos_dir / config.OPEN_SUBDIR
        self._completed_dir = self._todos_dir / config.COMPLETED_SUBDIR
        self._tz = tz or ZoneInfo(config.DEFAULT_TIMEZONE)

    # -- ownership helpers --------------------------------------------------

    @staticmethod
    def _managed_key(text: str) -> Optional[str]:
        """Return the managed key if `text` is a note we own, else None.

        Todo notes key on their `id`. Legacy hub notes (a prior version wrote one
        per project/person) carry the managed flag plus a `homeassist_hub` flag; we
        no longer write them, so they get a synthetic ``legacy_hub::…`` key that is
        never in the desired set — reconciliation then deletes them.
        """
        if not text.startswith("---"):
            return None
        end = text.find("\n---", 3)
        if end == -1:
            return None
        frontmatter = text[3:end]
        if not re.search(rf"^{re.escape(config.MANAGED_FLAG_KEY)}:\s*true\s*$",
                         frontmatter, re.MULTILINE):
            return None
        if re.search(rf"^{re.escape(config.HUB_FLAG_KEY)}:\s*\S+", frontmatter, re.MULTILINE):
            title = re.search(r"^title:\s*\"?([^\"\n]+)\"?\s*$", frontmatter, re.MULTILINE)
            return f"legacy_hub::{title.group(1).strip() if title else ''}"
        match = re.search(r"^id:\s*\"?([^\"\n]+)\"?\s*$", frontmatter, re.MULTILINE)
        return match.group(1).strip() if match else None

    def _index_managed_notes(self) -> Tuple[Dict[str, Path], List[Path]]:
        """Index managed notes under the Todos tree.

        Scans recursively (so notes are found regardless of subfolder, and a flat
        legacy layout migrates cleanly). Returns (key -> primary path, orphans):
        if more than one file claims the same key — e.g. a prior move whose unlink
        failed left a stale copy — one is kept (deterministically) and the rest are
        returned as orphans to delete, so the export self-heals duplicates.
        """
        index: Dict[str, Path] = {}
        orphans: List[Path] = []
        if not self._todos_dir.exists():
            return index, orphans
        for path in sorted(self._todos_dir.rglob("*.md")):
            try:
                key = self._managed_key(path.read_text(encoding="utf-8"))
            except OSError:
                continue
            if not key:
                continue
            if key in index:
                orphans.append(path)  # duplicate copy of an already-indexed note
            else:
                index[key] = path
        return index, orphans

    def _target_dir(self, todo: Mapping[str, Any]) -> Path:
        return self._completed_dir if todo.get("completed") else self._open_dir

    def _unique_path(self, todo: Mapping[str, Any], target_dir: Path, taken: set[Path]) -> Path:
        slug = markdown.slugify(str(todo.get("title") or ""))
        candidate = target_dir / f"{slug}.md"
        if candidate not in taken and not candidate.exists():
            return candidate
        suffix = str(todo.get("id") or "").rsplit("_", 1)[-1] or "todo"
        return target_dir / f"{slug}-{suffix}.md"

    def _resolve_path(
        self,
        todo: Mapping[str, Any],
        existing_path: Optional[Path],
        target_dir: Path,
        taken: set[Path],
    ) -> Path:
        """Where this todo's note belongs now. Keeps the filename when only the
        status folder changes (so wiki-backlinks by note name stay intact)."""
        if existing_path is not None:
            desired = target_dir / existing_path.name
            if desired == existing_path or (desired not in taken and not desired.exists()):
                return desired
        return self._unique_path(todo, target_dir, taken)

    def _links_for(
        self,
        todo: Mapping[str, Any],
        id_to_name: Dict[str, str],
        enrichment: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Frontmatter wikilink fields for this todo. Links to other todos are only
        emitted when the neighbour is part of this export (no dangling links)."""
        links: Dict[str, Any] = {}

        group = markdown.todo_group(todo)
        if group:
            links[config.FM_PROJECT] = markdown.wikilink_name(group)

        metadata = todo.get("source_metadata") or {}
        if isinstance(metadata, Mapping):
            parent = metadata.get("chain_parent_id")
            if parent and parent in id_to_name:
                links[config.FM_PREVIOUS] = id_to_name[parent]
            nxt = metadata.get("advanced_to")
            if nxt and nxt in id_to_name:
                links[config.FM_NEXT] = id_to_name[nxt]

        entry = enrichment.get(str(todo.get("id") or "")) if enrichment else None
        if entry is not None:
            related = [
                id_to_name[r] for r in getattr(entry, "related_ids", []) if r in id_to_name
            ]
            if related:
                links[config.FM_RELATED] = related
            people = [
                markdown.wikilink_name(p) for p in getattr(entry, "entities", []) if p
            ]
            if people:
                links[config.FM_PEOPLE] = people
        return links

    def _write_if_changed(self, path: Path, rendered: str, source: Optional[Path]) -> bool:
        """Write `rendered` to `path`, moving from `source` if needed. Returns True
        when a write happened (skips unchanged in-place notes to avoid re-index churn)."""
        moved = source is not None and source != path
        prior_text = source.read_text(encoding="utf-8") if source and source.exists() else (
            path.read_text(encoding="utf-8") if path.exists() else None
        )
        if not moved and rendered == prior_text:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
        if moved:
            source.unlink(missing_ok=True)
        return True

    # -- contract -----------------------------------------------------------

    def export_user_todos(
        self,
        *,
        user: str,
        todos: Sequence[Mapping[str, Any]],
        enrichment: Optional[Mapping[str, Any]] = None,
    ) -> ExportResult:
        try:
            existing, orphans = self._index_managed_notes()
            written = 0
            deleted = 0
            taken: set[Path] = set()
            desired_keys: set[str] = set()

            # Pass 1 — plan every todo's destination, building id -> note-name so
            # chain links can reference notes that come later in the list.
            plans: List[Tuple[Mapping[str, Any], Optional[Path], Path]] = []
            id_to_name: Dict[str, str] = {}
            for todo in todos:
                todo_id = str(todo.get("id") or "").strip()
                if not todo_id:
                    continue
                desired_keys.add(todo_id)
                existing_path = existing.get(todo_id)
                target_path = self._resolve_path(
                    todo, existing_path, self._target_dir(todo), taken
                )
                taken.add(target_path)
                plans.append((todo, existing_path, target_path))
                id_to_name[todo_id] = target_path.stem

            # Pass 2 — render with links and write/move.
            for todo, existing_path, target_path in plans:
                source = existing_path if existing_path and existing_path.exists() else None
                prior_text = source.read_text(encoding="utf-8") if source else None
                rendered = markdown.render_todo_document(
                    todo,
                    existing_text=prior_text,
                    tz=self._tz,
                    links=self._links_for(todo, id_to_name, enrichment),
                )
                if self._write_if_changed(target_path, rendered, source):
                    written += 1

            # Remove duplicate orphan copies (e.g. from a prior failed move).
            for path in orphans:
                path.unlink(missing_ok=True)
                deleted += 1

            # Remove managed notes no longer desired — todos that were deleted, and
            # legacy hub/person stubs from the prior structure (never desired now).
            for key, path in existing.items():
                if key not in desired_keys:
                    path.unlink(missing_ok=True)
                    deleted += 1

            return ExportResult(
                success=True,
                vault_path=str(self._vault_path),
                files_written=written,
                files_deleted=deleted,
            )
        except Exception as exc:  # never break the caller's pipeline
            logger.warning("Obsidian export failed for %s: %s", user, exc)
            return ExportResult(
                success=False, vault_path=str(self._vault_path), error=str(exc)
            )
