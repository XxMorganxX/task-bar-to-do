"""Config-driven wiring: hand back a TodoExporter, or None when export is off.

Call sites use this and depend only on the TodoExporter contract — they never
construct a concrete exporter or read the vault config themselves.
"""

from __future__ import annotations

from typing import Optional

from . import config
from .interface import TodoExporter
from .vault_exporter import ObsidianVaultExporter


def get_todo_exporter(
    enabled: Optional[bool] = None,
    vault_path: Optional[str] = None,
    todos_subdir: Optional[str] = None,
    tz=None,
) -> Optional[TodoExporter]:
    """Build the configured exporter, or None if disabled / no vault configured.

    Args override config/env (used by tests); when omitted, values come from
    `config` (which reads the OBSIDIAN_* env vars).
    """
    is_enabled = config.export_enabled() if enabled is None else enabled
    if not is_enabled:
        return None

    path = config.vault_path() if vault_path is None else vault_path
    if not path:
        return None

    subdir = config.todos_subdir() if todos_subdir is None else todos_subdir
    return ObsidianVaultExporter(vault_path=path, todos_subdir=subdir, tz=tz)
