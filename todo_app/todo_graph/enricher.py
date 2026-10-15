"""Orchestrates graph enrichment: entities (LLM, cached) + relatedness (embeddings).

Returns id -> TodoEnrichment for the exporter. Never raises into the caller — a
failure of either half degrades to empty data for that half.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import config
from . import entities as entities_mod
from .canonical import canonicalize_mapping
from .embeddings import EmbeddingIndex
from .interface import EntityExtractor, MetadataWriter
from .relatedness import top_related
from .types import TodoEnrichment

logger = logging.getLogger(__name__)


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return text or "unknown"


class GraphEnricher:
    def __init__(
        self,
        *,
        extractor: EntityExtractor,
        metadata_writer: Optional[MetadataWriter] = None,
        embedding_index_factory=None,
    ) -> None:
        self._extractor = extractor
        self._writer = metadata_writer
        # Injectable for tests; default builds a per-user cache-backed index.
        self._embedding_index_factory = embedding_index_factory or self._default_index

    @staticmethod
    def _default_index(user: str) -> EmbeddingIndex:
        cache_path = config.TODO_CACHE_ROOT / _slug(user) / config.EMBEDDING_CACHE_FILENAME
        return EmbeddingIndex(cache_path)

    # -- entities -----------------------------------------------------------

    def _entities_for(self, user: str, todos: Sequence[Mapping[str, Any]]) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        persist = self._writer is not None and self._extractor.name != "heuristic"
        for todo in todos:
            todo_id = str(todo.get("id") or "")
            if not todo_id:
                continue
            if not entities_mod.entities_stale(todo):
                result[todo_id] = entities_mod.cached_entities(todo)
                continue
            try:
                found = self._extractor.extract(todo)
            except Exception as exc:  # pragma: no cover - provider variance
                logger.warning("Entity extraction failed for %s: %s", todo_id, exc)
                found = []
            result[todo_id] = found
            if persist:
                payload = entities_mod.entities_cache_payload(found, todo)
                try:
                    self._writer.update_todo_metadata(
                        user=user,
                        todo_id=todo_id,
                        metadata_updates={config.GRAPH_METADATA_NAMESPACE: payload},
                    )
                    todo.setdefault("source_metadata", {}).setdefault(
                        config.GRAPH_METADATA_NAMESPACE, {}
                    ).update(payload)
                except Exception as exc:  # pragma: no cover
                    logger.warning("Persisting entities failed for %s: %s", todo_id, exc)
        return result

    # -- relatedness --------------------------------------------------------

    def _related_for(self, user: str, todos: Sequence[Mapping[str, Any]]) -> Dict[str, List[str]]:
        items = []
        for todo in todos:
            todo_id = str(todo.get("id") or "")
            text = f"{todo.get('title') or ''}\n{todo.get('details') or ''}".strip()
            if todo_id and text:
                items.append((todo_id, text, entities_mod.entities_input_hash(todo)))
        if len(items) < 2:
            return {}
        try:
            index = self._embedding_index_factory(user)
            vectors = index.vectors_for(items)
        except Exception as exc:  # pragma: no cover - provider variance
            logger.warning("Embedding/relatedness failed for %s: %s", user, exc)
            return {}
        return top_related(
            vectors,
            max_links=config.RELATED_MAX_LINKS,
            min_similarity=config.RELATED_MIN_SIMILARITY,
        )

    # -- public -------------------------------------------------------------

    def enrich(
        self, *, user: str, todos: Sequence[Mapping[str, Any]]
    ) -> Dict[str, TodoEnrichment]:
        entities = self._entities_for(user, todos) if config.entities_enabled() else {}
        if entities:
            # Consolidate name variants (ACME/Acme, aliases) across the whole set so
            # each entity is one graph node. Pure + post-cache → free to re-run.
            entities = canonicalize_mapping(entities, config.ENTITY_ALIASES)
        related = self._related_for(user, todos) if config.related_enabled() else {}

        out: Dict[str, TodoEnrichment] = {}
        for todo in todos:
            todo_id = str(todo.get("id") or "")
            if not todo_id:
                continue
            out[todo_id] = TodoEnrichment(
                entities=entities.get(todo_id, []),
                related_ids=related.get(todo_id, []),
            )
        return out


__all__ = ["GraphEnricher"]
