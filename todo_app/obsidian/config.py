"""Single source of truth for the Obsidian export: every tunable value, every
marker string, every env binding. Nothing elsewhere in the package should define
a path, marker, or default inline.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Env bindings (read live so tests and a reloaded process see current values)
# ---------------------------------------------------------------------------
_ENV_ENABLED = "OBSIDIAN_EXPORT_ENABLED"
_ENV_VAULT_PATH = "OBSIDIAN_VAULT_PATH"
_ENV_TODOS_SUBDIR = "OBSIDIAN_TODOS_SUBDIR"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_TODOS_SUBDIR = "Todos"          # folder inside the vault that holds todo notes
OPEN_SUBDIR = "Open"                     # open todos live in <Todos>/Open/
COMPLETED_SUBDIR = "Completed"           # completed todos live in <Todos>/Completed/
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIME_ZONE", "America/New_York")

# ---------------------------------------------------------------------------
# Markdown contract
# ---------------------------------------------------------------------------
# Machine-readable note kind. Maps onto the KB's `doc_kind` facet so the
# consolidation pipeline can gate todos out before building the mention graph.
DOC_KIND_KEY = "doc_kind"
DOC_KIND_TODO = "todo"

# Frontmatter flag marking a note as owned by the exporter. Only files carrying
# this flag are ever updated or deleted; hand-written notes are never touched.
MANAGED_FLAG_KEY = "homeassist_managed"

# Frontmatter link fields. Wikilinks here (not Dataview lines in the body) carry
# the graph signal without adding templated prose that poisons clustering.
FM_PROJECT = "project"      # todo's group   -> [[Project]]
FM_PEOPLE = "people"        # enrichment entities -> [[Person]] list
FM_RELATED = "related"      # embedding-similarity links (AI enrichment)
FM_PREVIOUS = "previous"    # chain parent
FM_NEXT = "next"            # chain next step

# Boundary between managed content (regenerated each export) and user content
# (preserved across syncs). A single hidden HTML comment — deliberately minimal so
# it adds almost no shared text to the embedded body.
USER_CONTENT_MARKER = "<!-- homeassist:end -->"

# ---- Legacy markers (recognized only for cleanup / migration) --------------
# Prior versions wrapped a templated task block in these and gave hub notes a
# `homeassist_hub` flag. We no longer write either, but still recognize them so
# old notes migrate (user tail preserved) and old hub stubs are deleted.
HUB_FLAG_KEY = "homeassist_hub"
MANAGED_BLOCK_END = "%% homeassist:todo:end %%"

# Filename slug ceiling (Obsidian/macOS filename friendliness).
FILENAME_MAX_SLUG_LEN = 80

# How many todos to export per refresh (matches the local cache limit).
EXPORT_LIMIT = 500


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def export_enabled() -> bool:
    return _env_bool(_ENV_ENABLED)


def vault_path() -> str:
    return os.getenv(_ENV_VAULT_PATH, "").strip()


def todos_subdir() -> str:
    return os.getenv(_ENV_TODOS_SUBDIR, "").strip() or DEFAULT_TODOS_SUBDIR
