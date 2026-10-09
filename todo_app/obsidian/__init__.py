"""One-way export of todos into an Obsidian vault as markdown notes.

HomeAssist stays the source of truth; the vault is a read/query surface — one note
per todo, all machinery in frontmatter, a clean body for clustering. Todo state is
never read back.

See tasks/redesign-obsidian-todo-notes.md for the current design contract.
"""

from .factory import get_todo_exporter
from .interface import ExportResult, TodoExporter

__all__ = ["get_todo_exporter", "TodoExporter", "ExportResult"]
