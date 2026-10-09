"""Single source of truth for todo graph enrichment: every flag, threshold, cap,
model, prompt, cache path, and metadata namespace. Nothing elsewhere in the package
defines these inline.
"""

from __future__ import annotations

import os
from pathlib import Path

from todo_app import settings

# ---------------------------------------------------------------------------
# Enable flags (env-driven; master is opt-in)
# ---------------------------------------------------------------------------
_ENV_ENABLED = "TODO_GRAPH_ENRICHMENT_ENABLED"


def enrichment_enabled() -> bool:
    return os.getenv(_ENV_ENABLED, "").strip().lower() in {"1", "true", "yes", "on"}


# Sub-toggles (default on when the master is on). Off lets you run one half only.
def entities_enabled() -> bool:
    return os.getenv("TODO_GRAPH_ENTITIES_ENABLED", "true").strip().lower() in {
        "1", "true", "yes", "on"
    }


def related_enabled() -> bool:
    return os.getenv("TODO_GRAPH_RELATED_ENABLED", "true").strip().lower() in {
        "1", "true", "yes", "on"
    }


# ---------------------------------------------------------------------------
# Metadata namespace (lives under todo.source_metadata.graph.*)
# ---------------------------------------------------------------------------
GRAPH_METADATA_NAMESPACE = "graph"

# ---------------------------------------------------------------------------
# Relatedness (embedding similarity)
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = os.getenv("TODO_GRAPH_EMBEDDING_MODEL", "text-embedding-3-small")
RELATED_MIN_SIMILARITY = 0.80   # cosine floor for a link (avoids a hairball graph)
RELATED_MAX_LINKS = 3           # most Related:: links emitted per todo
EMBEDDING_CACHE_FILENAME = "graph_embeddings.json"  # under the per-user todo cache dir
TODO_CACHE_ROOT = settings.TODO_STATE_ROOT

# ---------------------------------------------------------------------------
# Entity extraction (LLM)
# ---------------------------------------------------------------------------
ENTITY_MODEL = os.getenv("TODO_GRAPH_ENTITY_MODEL", "gpt-5.4-mini")
ENTITY_FALLBACK_MODEL = os.getenv("TODO_GRAPH_ENTITY_FALLBACK_MODEL", "gemini-2.5-flash")
ENTITY_TEMPERATURE = 0.0
ENTITY_MAX = 4                  # cap entities per todo (keeps the graph legible)

# Entity aliases — the easy merge knob. Map any variant (matched case-insensitively)
# to the canonical display name on the right. Case-only variants (LILY/Lily/lily) are
# merged automatically and need no entry here; use this for nicknames, abbreviations,
# and differing spellings. Example: "reid wade startup club": "Reid Wade".
ENTITY_ALIASES = {
    "lily": "Lily",
}
# Bump when the model or prompt changes so cached entities re-extract. The cache
# key folds this in, so a model/prompt swap invalidates stale results on next run.
ENTITY_PROMPT_VERSION = 3

ENTITY_SYSTEM_PROMPT = (
    "You extract the people and organizations a personal to-do is actually about, so "
    "that to-dos involving the same collaborator can be linked together.\n"
    "Return ONLY specific people or organizations the task involves — collaborators, "
    "recipients, stakeholders, or teams the user would work with or contact "
    "(e.g. 'Bill', 'Adam', the user's company).\n"
    "Do NOT extract:\n"
    "- URLs, domains, website or blog names, or the authors/owners of any linked "
    "content (a link to simonwillison.net is NOT a person named Simon Willison).\n"
    "- Products, tools, technologies, or vendors merely mentioned as a topic.\n"
    "- Generic words, roles, places, dates, or the task verb.\n"
    "Use the shortest natural canonical form, consistently capitalized. If none apply, "
    'return an empty list. Never invent. Respond as JSON: {"entities": ["Name", ...]}.'
)
ENTITY_USER_PROMPT_TEMPLATE = (
    "Title: {title}\nDetails: {details}\n\nExtract the people/organizations."
)

# ---------------------------------------------------------------------------
# Connection labels are owned by the exporter (obsidian.config); this package
# only produces the data (entities + related ids).
# ---------------------------------------------------------------------------
