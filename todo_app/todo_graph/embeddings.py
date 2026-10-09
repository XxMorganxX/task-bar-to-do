"""Embeddings for todos, with a local hash-keyed vector cache.

Only todos whose text (hash) isn't already cached get embedded, so steady-state
re-export costs ~zero. Wraps the async ``OpenAIEmbeddingProvider`` behind a sync
surface (the exporter runs on a background thread, not an event loop).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from . import config

logger = logging.getLogger(__name__)

# (id, text, hash) for one todo to embed.
EmbedItem = Tuple[str, str, str]


def _run_async(coro):
    """Run a coroutine to completion from a thread that has no event loop."""
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except Exception:  # pragma: no cover - defensive
        raise


class EmbeddingIndex:
    def __init__(
        self,
        cache_path,
        *,
        model: str = config.EMBEDDING_MODEL,
        provider=None,
    ) -> None:
        self._cache_path = Path(cache_path)
        self._model = model
        self._provider = provider  # injectable; lazily built when None
        self._cache: Dict[str, List[float]] = self._load()

    # -- cache io -----------------------------------------------------------

    def _load(self) -> Dict[str, List[float]]:
        if not self._cache_path.exists():
            return {}
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            return {k: v for k, v in data.items() if isinstance(v, list)}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(self._cache), encoding="utf-8")

    # -- provider -----------------------------------------------------------

    def _ensure_provider(self):
        if self._provider is None:
            try:
                from ..embedding import OpenAIEmbeddingProvider
            except ImportError:  # pragma: no cover - path variance
                from todo_app.embedding import OpenAIEmbeddingProvider
            provider = OpenAIEmbeddingProvider({"model": self._model})
            _run_async(provider.initialize())
            self._provider = provider
        return self._provider

    def _embed_batch(self, texts: Sequence[str]) -> List[List[float]]:
        provider = self._ensure_provider()
        return _run_async(provider.embed_batch(list(texts)))

    # -- public -------------------------------------------------------------

    def vectors_for(self, items: Sequence[EmbedItem]) -> Dict[str, List[float]]:
        """Return id -> vector for all items, embedding only uncached hashes and
        pruning the cache to the current set."""
        missing = [(i, text, h) for (i, text, h) in items if h not in self._cache]
        if missing:
            try:
                embedded = self._embed_batch([text for (_i, text, _h) in missing])
                for (_i, _text, h), vector in zip(missing, embedded):
                    self._cache[h] = vector
            except Exception as exc:
                logger.warning("Embedding batch failed: %s", exc)

        current_hashes = {h for (_i, _text, h) in items}
        if current_hashes != set(self._cache):
            self._cache = {h: v for h, v in self._cache.items() if h in current_hashes}
        self._save()

        return {i: self._cache[h] for (i, _text, h) in items if h in self._cache}


__all__ = ["EmbeddingIndex", "EmbedItem"]
