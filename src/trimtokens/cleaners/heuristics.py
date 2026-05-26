"""Heuristiques de filtrage intelligent des pages PDF.

Détecte les pages non pertinentes pour réduire les tokens sans perdre d'information
utile :
- TOC (Table of Contents)
- Bibliographie / Références
- Pages éparses (< N mots utiles)

Chaque détecteur est pur (fonction d'analyse) et retourne un booléen + raison.
L'orchestrateur `analyze_pages()` aggrège les résultats en `PageAnalysis` par page.

Le filtrage est OPT-IN via `ExtractOptions.smart_filter=True`. Comportement par
défaut inchangé.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- Constantes module ----------------------------------------------------

# Pattern ligne "Texte ........ 42" ou "Texte    42" — typique d'un TOC
_TOC_LINE_RE = re.compile(
    r"^\s*\S.{1,120}?(?:\.{3,}|\s{4,}|\t+)\s*\d{1,4}\s*$",
    re.MULTILINE,
)

# Titre de section TOC
_TOC_TITLE_RE = re.compile(
    r"\b(?:sommaire|table\s+des\s+mati[èe]res|table\s+of\s+contents|contents)\b",
    re.IGNORECASE,
)

# Titre de section bibliographie
_BIBLIO_TITLE_RE = re.compile(
    r"\b(?:bibliographie|r[ée]f[ée]rences(?:\s+bibliographiques)?|references|"
    r"works\s+cited|sources(?:\s+cit[ée]es)?|webographie)\b",
    re.IGNORECASE,
)

# Patterns de références : [N], (Auteur, 2024), Auteur, J. (2024)
_REF_BRACKET_RE = re.compile(r"\[\d{1,4}\]")
_REF_AUTHOR_YEAR_RE = re.compile(r"\([A-Z][a-zéèêA-Z]+(?:\s+(?:et\s+al\.?|&)\s*[A-Z]?[a-z]*)?,?\s+\d{4}\)")
_REF_NUMBERED_LINE_RE = re.compile(r"^\s*\d{1,3}\.\s+[A-Z]", re.MULTILINE)

# Seuils par défaut (configurables via ExtractOptions plus tard si besoin)
TOC_MIN_LINES = 5  # ≥ 5 lignes "texte ... N" pour déclencher
BIBLIO_MIN_REFS = 8  # ≥ 8 références sur la page
SPARSE_MIN_WORDS = 30  # < 30 mots = page éparse


# --- Modèle ---------------------------------------------------------------


@dataclass
class PageAnalysis:
    """Analyse d'une page : indicateurs heuristiques + raisons."""

    page_index: int  # 0-based
    word_count: int
    is_toc: bool = False
    is_bibliography: bool = False
    is_sparse: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def should_filter(self) -> bool:
        """True si la page doit être exclue de la sortie."""
        return self.is_toc or self.is_bibliography or self.is_sparse


# --- Détecteurs individuels ----------------------------------------------


def detect_toc(text: str) -> tuple[bool, str]:
    """Détecte si la page est une table des matières.

    Critères :
    - Titre `Sommaire`/`Table des matières`/`Table of contents`/`Contents`, OU
    - ≥ TOC_MIN_LINES lignes au format `texte ... numéro` ou `texte    numéro`
    """
    if _TOC_TITLE_RE.search(text):
        return True, "titre TOC détecté"

    matches = _TOC_LINE_RE.findall(text)
    if len(matches) >= TOC_MIN_LINES:
        return True, f"{len(matches)} lignes de type TOC"

    return False, ""


def detect_bibliography(text: str) -> tuple[bool, str]:
    """Détecte si la page contient une bibliographie / liste de références.

    Critères :
    - Titre `Bibliographie`/`Références`/`References`/`Sources citées`, OU
    - ≥ BIBLIO_MIN_REFS occurrences de patterns de références sur la page
    """
    if _BIBLIO_TITLE_RE.search(text):
        return True, "titre Bibliographie détecté"

    bracket = len(_REF_BRACKET_RE.findall(text))
    author_year = len(_REF_AUTHOR_YEAR_RE.findall(text))
    numbered = len(_REF_NUMBERED_LINE_RE.findall(text))
    total = bracket + author_year + numbered

    if total >= BIBLIO_MIN_REFS:
        return True, f"{total} références ({bracket} [N], {author_year} (auteur,année), {numbered} numérotées)"

    return False, ""


def detect_sparse(text: str, word_count: int) -> tuple[bool, str]:
    """Détecte une page éparse (peu de mots utiles).

    Critères : moins de SPARSE_MIN_WORDS mots, hors espaces et ponctuation pure.
    """
    if word_count < SPARSE_MIN_WORDS:
        return True, f"{word_count} mots (seuil {SPARSE_MIN_WORDS})"
    return False, ""


# --- Orchestrateur --------------------------------------------------------


def analyze_pages(
    pages: list[str],
    *,
    filter_toc: bool = True,
    filter_bibliography: bool = True,
    filter_sparse: bool = True,
) -> list[PageAnalysis]:
    """Analyse toutes les pages et retourne une liste de `PageAnalysis`.

    Les flags `filter_*` activent/désactivent chaque détecteur individuellement.
    """
    analyses: list[PageAnalysis] = []

    for idx, page_text in enumerate(pages):
        word_count = len(page_text.split())
        analysis = PageAnalysis(page_index=idx, word_count=word_count)

        if filter_toc:
            is_toc, reason = detect_toc(page_text)
            if is_toc:
                analysis.is_toc = True
                analysis.reasons.append(f"TOC : {reason}")

        if filter_bibliography:
            is_biblio, reason = detect_bibliography(page_text)
            if is_biblio:
                analysis.is_bibliography = True
                analysis.reasons.append(f"Bibliographie : {reason}")

        if filter_sparse and not analysis.is_toc and not analysis.is_bibliography:
            is_sparse, reason = detect_sparse(page_text, word_count)
            if is_sparse:
                analysis.is_sparse = True
                analysis.reasons.append(f"Éparse : {reason}")

        analyses.append(analysis)

    return analyses


def filter_pages(
    pages: list[str],
    analyses: list[PageAnalysis],
) -> tuple[list[str], dict[str, list[int]]]:
    """Filtre les pages selon les analyses.

    Retourne :
    - liste des pages conservées (sans les pages filtrées)
    - dict des pages filtrées par catégorie (1-indexed pour affichage utilisateur) :
      `{"toc": [...], "bibliography": [...], "sparse": [...]}`
    """
    kept: list[str] = []
    filtered: dict[str, list[int]] = {"toc": [], "bibliography": [], "sparse": []}

    for page_text, analysis in zip(pages, analyses, strict=True):
        if not analysis.should_filter:
            kept.append(page_text)
            continue

        page_num = analysis.page_index + 1  # 1-indexed
        if analysis.is_toc:
            filtered["toc"].append(page_num)
        elif analysis.is_bibliography:
            filtered["bibliography"].append(page_num)
        elif analysis.is_sparse:
            filtered["sparse"].append(page_num)

    return kept, filtered
