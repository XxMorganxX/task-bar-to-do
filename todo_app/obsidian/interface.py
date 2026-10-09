"""The export contract. Call sites depend on TodoExporter, never on a concrete
vault/markdown implementation, so the export target can be swapped via the factory.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence


@dataclass
class ExportResult:
    """Outcome of exporting one user's todos."""

    success: bool
    vault_path: str
    files_written: int = 0
    files_deleted: int = 0
    error: Optional[str] = None


class TodoExporter(ABC):
    """Exports a user's full todo set to an external surface (one-way)."""

    @abstractmethod
    def export_user_todos(
        self,
        *,
        user: str,
        todos: Sequence[Mapping[str, Any]],
        enrichment: Optional[Mapping[str, Any]] = None,
    ) -> ExportResult:
        """Reconcile the export target with `todos` (the complete current set).

        Implementations create/update entries for the given todos and remove
        previously-exported entries that are no longer present. `enrichment`
        optionally maps todo id -> connection data (entities, related ids). Must
        never raise for ordinary IO problems — return ExportResult(success=False).
        """
        raise NotImplementedError
