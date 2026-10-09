"""Pure data types for todo graph enrichment. No I/O, stdlib only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class TodoEnrichment:
    """AI-derived connection data for one todo, consumed by the exporter.

    `entities` are people/org names → rendered as ``Person:: [[Name]]``.
    `related_ids` are other todo ids → rendered as ``Related:: [[note]]`` after the
    exporter resolves each id to its note name (ids absent from the export are dropped).
    """

    entities: List[str] = field(default_factory=list)
    related_ids: List[str] = field(default_factory=list)


__all__ = ["TodoEnrichment"]
