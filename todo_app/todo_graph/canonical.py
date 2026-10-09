"""Consolidate entity name variants into one canonical name.

Two layers, applied in order:
  1. Explicit aliases (config.ENTITY_ALIASES) — user-editable forced merges,
     matched case-insensitively. The value is the canonical display name.
  2. Automatic case-merge — names identical ignoring case collapse to one casing,
     preferring a mixed-case form ("Lily") over ALL-CAPS/all-lower ("LILY"/"lily").
     A name with no case-variant is left untouched, so acronyms ("AWS") survive.

Pure: deterministic, no I/O, no model calls. Runs after cached extraction, so
editing the alias map re-resolves links for free on the next export.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable, List, Mapping, Sequence


def _alias_resolved(name: str, aliases: Mapping[str, str]) -> str:
    key = name.strip().lower()
    return aliases.get(key, name.strip())


def _is_mixed_case(text: str) -> bool:
    return any(c.islower() for c in text) and any(c.isupper() for c in text)


def canonical_map(names: Iterable[str], aliases: Mapping[str, str]) -> Dict[str, str]:
    """Map every input name (as given) to its canonical form."""
    resolved: Dict[str, str] = {}
    for name in names:
        if name and name.strip():
            resolved[name] = _alias_resolved(name, aliases)

    freq = Counter(resolved.values())

    # Group resolved forms by case-insensitive key, pick the best casing per group.
    groups: Dict[str, set] = {}
    for form in resolved.values():
        groups.setdefault(form.casefold(), set()).add(form)

    canonical_for_key: Dict[str, str] = {}
    for key, forms in groups.items():
        # Prefer mixed-case, then most frequent, then alphabetical (determinism).
        canonical_for_key[key] = sorted(
            forms, key=lambda f: (not _is_mixed_case(f), -freq[f], f)
        )[0]

    return {orig: canonical_for_key[res.casefold()] for orig, res in resolved.items()}


def _dedupe_preserving_order(names: Sequence[str]) -> List[str]:
    seen: set = set()
    out: List[str] = []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def canonicalize_mapping(
    entities_by_id: Mapping[str, Sequence[str]], aliases: Mapping[str, str]
) -> Dict[str, List[str]]:
    """Apply canonicalization across all todos' entities at once (so the canonical
    casing is consistent everywhere), returning id -> canonical, de-duped names."""
    all_names = [n for names in entities_by_id.values() for n in names]
    cmap = canonical_map(all_names, aliases)
    return {
        todo_id: _dedupe_preserving_order([cmap.get(n, n) for n in names])
        for todo_id, names in entities_by_id.items()
    }


__all__ = ["canonical_map", "canonicalize_mapping"]
