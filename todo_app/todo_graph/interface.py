"""Contracts the enricher depends on. The enricher never references a concrete
LLM provider or the TodoManager directly — only these abstractions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class EntityExtractor(ABC):
    """Extract person/org names from a todo."""

    name: str = "entity-extractor"

    @abstractmethod
    def extract(self, todo: Dict[str, Any]) -> List[str]:
        """Return canonical entity names (possibly empty). Must not raise."""
        raise NotImplementedError


@runtime_checkable
class MetadataWriter(Protocol):
    """The slice of TodoManager the enricher needs to persist cached metadata."""

    def update_todo_metadata(
        self,
        *,
        user: Optional[str],
        todo_id: Optional[str],
        metadata_updates: Dict[str, Any],
        merge: bool = True,
    ) -> Dict[str, Any]:
        ...
