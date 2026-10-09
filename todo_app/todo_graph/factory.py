"""Config-driven wiring for graph enrichment. Returns a GraphEnricher, or None
when enrichment is disabled. Call sites depend on this, not the concrete pieces.
"""

from __future__ import annotations

from typing import Optional

from . import config
from .entities import make_entity_extractor
from .enricher import GraphEnricher
from .interface import MetadataWriter


def get_graph_enricher(
    metadata_writer: Optional[MetadataWriter] = None,
    *,
    enabled: Optional[bool] = None,
) -> Optional[GraphEnricher]:
    """Build the enricher if enrichment is on, else None. `metadata_writer` (a
    TodoManager) lets the enricher cache entity results back onto the todo."""
    is_enabled = config.enrichment_enabled() if enabled is None else enabled
    if not is_enabled:
        return None
    return GraphEnricher(
        extractor=make_entity_extractor(),
        metadata_writer=metadata_writer,
    )


__all__ = ["get_graph_enricher"]
