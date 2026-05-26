"""Package GUI TrimTokens (MVVM léger).

Layout :
- `utils`   — helpers purs (parsing, formatage, OS) testables sans Tk
- `state`   — `AppState` + `FileResult` dataclasses
- `services` — `ProcessingService` (thread + callbacks)
- `app`     — `TrimTokensGUI` view + handlers + entry point `main`

Compat surface API : tous les noms historiques (`TrimTokensGUI`, `main`,
`_parse_dropped_paths`, `_format_bytes`, `_format_count`, `_open_in_explorer`,
`SUPPORTED_LANGUAGES`) restent importables via `trimtokens.gui`.
"""

from __future__ import annotations

from trimtokens.gui.app import TrimTokensGUI, main
from trimtokens.gui.services import (
    ProcessingCallbacks,
    ProcessingService,
)
from trimtokens.gui.state import AppState, FileResult
from trimtokens.gui.utils import (
    SUPPORTED_LANGUAGES,
    _format_bytes,
    _format_count,
    _open_in_explorer,
    _parse_dropped_paths,
)

__all__ = [
    "SUPPORTED_LANGUAGES",
    "AppState",
    "FileResult",
    "ProcessingCallbacks",
    "ProcessingService",
    "TrimTokensGUI",
    "_format_bytes",
    "_format_count",
    "_open_in_explorer",
    "_parse_dropped_paths",
    "main",
]
