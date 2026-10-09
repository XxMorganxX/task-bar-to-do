"""Entity (person/org) extraction for todos, with an input-hash cache.

Mirrors the reminders Classifier chain: OpenAI (primary) -> Gemini -> heuristic.
The heuristic returns [] — entities are only added when an LLM is available, never
fabricated. Cached on the todo's `graph` metadata; re-run only when text changes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from . import config
from .interface import EntityExtractor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalization + cache (pure)
# ---------------------------------------------------------------------------

def normalize_entities(raw: Any) -> List[str]:
    """Clean, dedupe (case-insensitive, first wins), and cap a raw entity list."""
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: List[str] = []
    for item in raw:
        name = re.sub(r"\s+", " ", str(item or "")).strip().strip("#[]|")
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
        if len(out) >= config.ENTITY_MAX:
            break
    return out


def entities_input_hash(todo: Dict[str, Any]) -> str:
    """Cache key over the inputs AND the extraction config (model + prompt version),
    so changing the model or prompt invalidates cached entities and forces re-extraction."""
    title = (todo.get("title") or "").strip().lower()
    details = (todo.get("details") or "").strip().lower()
    salt = f"{config.ENTITY_MODEL}\x1f{config.ENTITY_PROMPT_VERSION}"
    payload = f"{title}\x1f{details}\x1f{salt}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _graph_meta(todo: Dict[str, Any]) -> Dict[str, Any]:
    meta = todo.get("source_metadata") or {}
    if isinstance(meta, dict):
        graph = meta.get(config.GRAPH_METADATA_NAMESPACE)
        if isinstance(graph, dict):
            return graph
    return {}


def entities_stale(todo: Dict[str, Any]) -> bool:
    graph = _graph_meta(todo)
    if "entities" not in graph or "entities_input_hash" not in graph:
        return True
    return graph.get("entities_input_hash") != entities_input_hash(todo)


def cached_entities(todo: Dict[str, Any]) -> List[str]:
    return normalize_entities(_graph_meta(todo).get("entities"))


def entities_cache_payload(entities: List[str], todo: Dict[str, Any]) -> Dict[str, Any]:
    """Fields to persist under the `graph` namespace for entity caching."""
    return {"entities": entities, "entities_input_hash": entities_input_hash(todo)}


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------

class HeuristicEntityExtractor(EntityExtractor):
    name = "heuristic"

    def extract(self, todo: Dict[str, Any]) -> List[str]:
        return []  # never fabricate entities without a model


class OpenAIEntityExtractor(EntityExtractor):
    name = "openai"

    def __init__(self, api_key: Optional[str] = None):
        from openai import OpenAI

        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIEntityExtractor")
        self._client = OpenAI(api_key=api_key)
        self._fallback = _build_fallback()

    def extract(self, todo: Dict[str, Any]) -> List[str]:
        prompt = config.ENTITY_USER_PROMPT_TEMPLATE.format(
            title=todo.get("title") or "",
            details=todo.get("details") or "(none)",
        )
        messages = [
            {"role": "system", "content": config.ENTITY_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        try:
            data = _parse_json(self._complete(messages))
            return normalize_entities(data.get("entities"))
        except Exception as exc:  # pragma: no cover - network/parse variance
            logger.warning("OpenAI entity extraction failed, falling back: %s", exc)
            return self._fallback.extract(todo)

    def _complete(self, messages: Any) -> str:
        kwargs: Dict[str, Any] = {
            "model": config.ENTITY_MODEL,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": config.ENTITY_TEMPERATURE,
        }
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            # gpt-5 reasoning minis reject a custom temperature; retry with the
            # API default before deferring to the fallback chain.
            if "temperature" in str(exc).lower():
                kwargs.pop("temperature", None)
                response = self._client.chat.completions.create(**kwargs)
            else:
                raise
        return response.choices[0].message.content or ""


class GeminiEntityExtractor(EntityExtractor):
    name = "gemini"

    def __init__(self, api_key: Optional[str] = None):
        import google.generativeai as genai

        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for GeminiEntityExtractor")
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            config.ENTITY_FALLBACK_MODEL,
            generation_config={
                "temperature": config.ENTITY_TEMPERATURE,
                "response_mime_type": "application/json",
            },
            system_instruction=config.ENTITY_SYSTEM_PROMPT,
        )
        self._fallback = HeuristicEntityExtractor()

    def extract(self, todo: Dict[str, Any]) -> List[str]:
        prompt = config.ENTITY_USER_PROMPT_TEMPLATE.format(
            title=todo.get("title") or "",
            details=todo.get("details") or "(none)",
        )
        try:
            response = self._model.generate_content(prompt)
            data = _parse_json(getattr(response, "text", "") or "")
            return normalize_entities(data.get("entities"))
        except Exception as exc:  # pragma: no cover - network/parse variance
            logger.warning("Gemini entity extraction failed, using heuristic: %s", exc)
            return self._fallback.extract(todo)


def _parse_json(text: str) -> Dict[str, Any]:
    cleaned = re.sub(r"```$", "", re.sub(r"^```(?:json)?", "", text.strip()).strip()).strip()
    if not cleaned:
        return {}
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        return json.loads(match.group(0)) if match else {}


def _build_fallback() -> EntityExtractor:
    if os.getenv("GEMINI_API_KEY"):
        try:
            return GeminiEntityExtractor()
        except Exception as exc:  # pragma: no cover
            logger.warning("GeminiEntityExtractor unavailable: %s", exc)
    return HeuristicEntityExtractor()


def make_entity_extractor(prefer_llm: bool = True) -> EntityExtractor:
    """OpenAI -> Gemini -> heuristic, matching the reminders classifier chain."""
    if prefer_llm and os.getenv("OPENAI_API_KEY"):
        try:
            return OpenAIEntityExtractor()
        except Exception as exc:  # pragma: no cover
            logger.warning("OpenAIEntityExtractor unavailable, trying Gemini: %s", exc)
    if prefer_llm and os.getenv("GEMINI_API_KEY"):
        try:
            return GeminiEntityExtractor()
        except Exception as exc:  # pragma: no cover
            logger.warning("GeminiEntityExtractor unavailable, using heuristic: %s", exc)
    return HeuristicEntityExtractor()


__all__ = [
    "EntityExtractor",
    "HeuristicEntityExtractor",
    "OpenAIEntityExtractor",
    "GeminiEntityExtractor",
    "make_entity_extractor",
    "normalize_entities",
    "entities_input_hash",
    "entities_stale",
    "cached_entities",
    "entities_cache_payload",
]
