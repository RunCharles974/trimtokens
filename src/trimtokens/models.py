"""Dataclasses du domaine TrimTokens."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class ExtractOptions:
    ocr_languages: str = "fra+eng"
    ocr_psm: int = 6
    no_ocr: bool = False
    force_ocr: bool = False
    aggressive: bool = False
    workers: int = 0
    use_cache: bool = True
    max_chars: int = 0
    # Filtrage intelligent (opt-in) — PDF uniquement pour le moment
    smart_filter: bool = False
    filter_toc: bool = True
    filter_bibliography: bool = True
    filter_sparse: bool = True
    # Drop automatique des pages quasi-vides (< empty_page_min_words mots),
    # actif par défaut, indépendant du smart_filter. Cible les pages blanches
    # ou réduites à un numéro de page après OCR.
    drop_empty_pages: bool = True
    empty_page_min_words: int = 5
    # Fusion paragraphes inter-pages : si page N termine sans ponctuation finale
    # et page N+1 commence en minuscule, on supprime le header `## Page N+1`
    # et on enchaîne le texte. Améliore la lisibilité LLM.
    merge_continuations: bool = True
    # Seuils PDF/OCR — externalisés pour permettre tuning sans modifier le code.
    # Valeurs par défaut alignées sur les constantes historiques de pdf.py.
    pdf_min_native_chars_per_page: int = 50
    pdf_ocr_dpi: int = 300
    pdf_image_based_max_chars_per_page: int = 100
    pdf_image_based_min_images_per_page: int = 2
    pdf_image_based_min_pages: int = 3
    # Backend OCR (registry `ocr.backend.get_backend(name)`). Défaut : Tesseract.
    # Autres impls possibles via `register_backend(...)` : EasyOCR, PaddleOCR, cloud, …
    ocr_backend: str = "tesseract"


@dataclass
class Section:
    header: str
    content: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class ExtractedDocument:
    source_path: Path
    source_type: str
    title: str | None = None
    sections: list[Section] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    ocr_used: bool = False
    ocr_pages: list[int] = field(default_factory=list)


@dataclass
class CleanStats:
    original_size_bytes: int = 0
    cleaned_size_bytes: int = 0
    original_chars: int = 0
    cleaned_chars: int = 0
    tokens_estimated: int = 0
    tokens_original_estimated: int = 0
    # Estimation tokens si l'utilisateur uploade le fichier BRUT à Claude
    # (PDF binaire, image, etc.). Baseline ≈ taille_bytes / 4.
    # Cette métrique reflète l'économie réelle vs upload direct du fichier source,
    # alors que `tokens_original_estimated` reflète seulement le gain du nettoyage
    # par rapport au texte déjà extrait.
    tokens_input_estimated: int = 0
    duration_seconds: float = 0.0

    @property
    def reduction_percent(self) -> float:
        if self.original_size_bytes == 0:
            return 0.0
        return round((1 - self.cleaned_size_bytes / self.original_size_bytes) * 100, 2)

    @property
    def tokens_reduction_percent(self) -> float:
        if self.tokens_original_estimated == 0:
            return 0.0
        return round((1 - self.tokens_estimated / self.tokens_original_estimated) * 100, 2)

    @property
    def tokens_input_reduction_percent(self) -> float:
        """Gain tokens vs upload brut du fichier source (la métrique 'visible' user)."""
        if self.tokens_input_estimated == 0:
            return 0.0
        return round((1 - self.tokens_estimated / self.tokens_input_estimated) * 100, 2)


@dataclass
class ProcessResult:
    """Résultat complet d'un traitement document : document nettoyé + stats + Markdown rendu.

    `pipeline_metrics` : métriques agrégées par étape de nettoyage (chars in/out,
    durée). Vide par défaut ; rempli par `core.process` (négligeable, ~µs).
    Consommée par le flag CLI `--profile` pour afficher un breakdown.
    """

    document: ExtractedDocument
    stats: CleanStats
    markdown: str
    pipeline_metrics: list[object] = field(default_factory=list)  # list[StepMetrics]
