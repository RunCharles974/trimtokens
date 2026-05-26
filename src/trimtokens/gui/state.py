"""État applicatif GUI (cf audit §GUI "Introduire un état applicatif explicite").

Découple les données affichées des widgets Tk. Mutations passent par `AppState`,
la View se rebind après chaque tick via le contrôleur. Pas de logique métier ici.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileResult:
    """Résultat de traitement d'un fichier individuel.

    Remplace l'ancien `dict[str, Any]` non typé. Compat lecture clé style dict
    préservée pour les sites externes (recap legacy) via la méthode `__getitem__`.
    """

    file: str
    target: Path | None
    size_before: int = 0
    size_after: int = 0
    tokens_before: int = 0
    tokens_after: int = 0
    reduction: float = 0.0
    tokens_reduction: float = 0.0
    duration: float = 0.0
    status: str = "✓"

    def __getitem__(self, key: str) -> object:
        return getattr(self, key)


@dataclass
class AppState:
    """Snapshot mutable de l'état GUI.

    Champs touchés :
    - `processing` : True pendant qu'un batch s'exécute (UI verrouille drop).
    - `output_dir` : dossier de sortie du dernier batch (bouton "Ouvrir dossier").
    - `results` : log structuré des fichiers traités (alimente la recap).
    - `log_line_targets` : ligne du journal → fichier produit (double-clic visionneuse).
    - `current_viewer_path` : fichier actuellement chargé dans la visionneuse.
    """

    processing: bool = False
    output_dir: Path | None = None
    results: list[FileResult] = field(default_factory=list)
    log_line_targets: dict[int, Path] = field(default_factory=dict)
    current_viewer_path: Path | None = None

    def reset_batch(self) -> None:
        """Nettoie avant un nouveau batch (`results` + state intermédiaire)."""
        self.results.clear()
        # log_line_targets préservé tant que la fenêtre reste ouverte : permet
        # de double-cliquer sur d'anciennes lignes du journal sans confusion.


__all__ = ["AppState", "FileResult"]
