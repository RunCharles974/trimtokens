"""Pipeline de nettoyage 11 étapes.

Étapes (ordre exact, cf TrimTokens.md §4) :
1.  Normalisation Unicode NFKC
2.  Suppression caractères invisibles (zero-width, BOM, soft hyphen, contrôles non imprimables)
3.  Conversion ligatures typographiques (ﬁ ﬂ ﬀ ﬃ ﬄ)
4.  Recollage mots coupés en fin de ligne (`exem-\\nple` → `exemple`)
5.  Espaces multiples / tabulations → un seul espace
6.  Sauts de ligne consécutifs limités à 2 maximum
7.  Suppression en-têtes/pieds de page récurrents (≥30 % des pages OU `^Page \\d+`)
8.  Déduplication paragraphes identiques (≥3 occurrences)
9.  Suppression lignes ne contenant que ponctuation/séparateurs
10. Trim final + normalisation EOL → `\\n`
11. Estimation tokens (déléguée à `stats.compute_stats`)
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import TYPE_CHECKING

from trimtokens.models import CleanStats
from trimtokens.stats import compute_stats

if TYPE_CHECKING:
    from trimtokens.cleaners.steps import Pipeline, StepMetrics

# --- Constantes module ----------------------------------------------------

INVISIBLE_CHARS = frozenset(
    {
        "​",  # zero-width space
        "‌",  # zero-width non-joiner
        "‍",  # zero-width joiner
        "⁠",  # word joiner
        "﻿",  # zero-width no-break space (BOM)
        "­",  # soft hyphen
    }
)

LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "ft",
    "ﬆ": "st",
}

_HYPHEN_BREAK_RE = re.compile(r"(\w+)-\n(\w+)")
_INLINE_WS_RE = re.compile(r"[ 	 ]+")
_TRAILING_WS_RE = re.compile(r"[ \t]+\n")
_LEADING_WS_RE = re.compile(r"\n[ \t]+")
_PAGE_NUM_RE = re.compile(r"^\s*(?:page|p\.?)\s*\d+(?:\s*[/-]\s*\d+)?\s*$", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"^[-_*=~]{3,}$")
_PUNCT_ONLY_RE = re.compile(r"^[\s\W_]+$", re.UNICODE)


# --- Étapes individuelles -------------------------------------------------


def normalize_unicode(text: str) -> str:
    """Étape 1 : normalisation NFKC."""
    return unicodedata.normalize("NFKC", text)


def strip_invisibles(text: str) -> str:
    """Étape 2 : retire zero-width, BOM, soft hyphen, contrôles non imprimables.

    Conserve `\\t`, `\\n`, `\\r` qui sont structurellement utiles.
    """
    chars: list[str] = []
    for ch in text:
        if ch in INVISIBLE_CHARS:
            continue
        if ch in "\t\n\r":
            chars.append(ch)
            continue
        if unicodedata.category(ch)[0] == "C":
            continue
        chars.append(ch)
    return "".join(chars)


def convert_ligatures(text: str) -> str:
    """Étape 3 : remplace ligatures typographiques par leurs composantes."""
    for ligature, replacement in LIGATURES.items():
        text = text.replace(ligature, replacement)
    return text


def rejoin_hyphenated(text: str) -> str:
    """Étape 4 : recolle les mots coupés en fin de ligne (`exem-\\nple` → `exemple`)."""
    return _HYPHEN_BREAK_RE.sub(r"\1\2", text)


def collapse_whitespace(text: str) -> str:
    """Étape 5 : espaces multiples / tabulations → un seul espace.

    Préserve les sauts de ligne, mais supprime les espaces en début/fin de ligne.
    """
    text = _INLINE_WS_RE.sub(" ", text)
    text = _TRAILING_WS_RE.sub("\n", text)
    text = _LEADING_WS_RE.sub("\n", text)
    return text


def limit_consecutive_newlines(text: str, max_consecutive: int = 2) -> str:
    """Étape 6 : limite les sauts de ligne consécutifs à `max_consecutive`."""
    pattern = re.compile(r"\n{" + str(max_consecutive + 1) + r",}")
    return pattern.sub("\n" * max_consecutive, text)


def strip_recurring_headers_footers(pages: list[str], threshold: float = 0.30) -> list[str]:
    """Étape 7 : retire en-têtes/pieds de page récurrents sur plusieurs pages.

    Une ligne est considérée récurrente si :
    - elle apparaît dans le top-3 ou bottom-3 d'au moins `threshold` × len(pages) pages, OU
    - elle matche un pattern de numérotation de page (`Page N`, `Page N / M`).
    """
    if len(pages) < 3:
        # Pas assez de pages pour détecter une récurrence statistique.
        cleaned = []
        for page in pages:
            lines = [line for line in page.splitlines() if not _PAGE_NUM_RE.match(line.strip())]
            cleaned.append("\n".join(lines))
        return cleaned

    line_counts: Counter[str] = Counter()
    page_lines: list[list[str]] = []
    for page in pages:
        lines = page.splitlines()
        page_lines.append(lines)
        candidates: set[str] = set()
        non_empty = [line.strip() for line in lines if line.strip()]
        for line in non_empty[:3]:
            candidates.add(line)
        for line in non_empty[-3:]:
            candidates.add(line)
        for candidate in candidates:
            line_counts[candidate] += 1

    min_occurrences = max(2, int(len(pages) * threshold))
    recurring = {line for line, count in line_counts.items() if count >= min_occurrences}

    cleaned_pages: list[str] = []
    for lines in page_lines:
        kept: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped in recurring:
                continue
            if _PAGE_NUM_RE.match(stripped):
                continue
            kept.append(line)
        cleaned_pages.append("\n".join(kept))
    return cleaned_pages


def dedup_paragraphs(text: str, min_occurrences: int = 3) -> str:
    """Étape 8 : déduplique les paragraphes apparaissant ≥ `min_occurrences` fois.

    Conserve la première occurrence, supprime les suivantes.
    """
    paragraphs = text.split("\n\n")
    counts: Counter[str] = Counter(p.strip() for p in paragraphs if p.strip())
    seen: Counter[str] = Counter()
    result: list[str] = []
    for paragraph in paragraphs:
        key = paragraph.strip()
        if not key:
            result.append(paragraph)
            continue
        if counts[key] >= min_occurrences:
            seen[key] += 1
            if seen[key] > 1:
                continue
        result.append(paragraph)
    return "\n\n".join(result)


def strip_punctuation_only_lines(text: str) -> str:
    """Étape 9 : retire les lignes ne contenant que ponctuation ou séparateurs."""
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append(line)
            continue
        if _SEPARATOR_RE.match(stripped):
            continue
        if _PUNCT_ONLY_RE.match(stripped) and len(stripped) >= 3:
            continue
        kept.append(line)
    return "\n".join(kept)


def finalize(text: str) -> str:
    """Étape 10 : trim final + normalisation EOL → `\\n`."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


# --- Orchestrateur principal ----------------------------------------------


def clean(
    text: str | None = None,
    *,
    pages: list[str] | None = None,
    aggressive: bool = False,
    original_size_bytes: int = 0,
    pipeline: Pipeline | None = None,
    metrics_sink: list[StepMetrics] | None = None,
) -> tuple[str, CleanStats]:
    """Applique les 11 étapes de nettoyage.

    Fournir soit `text` (texte mono-bloc), soit `pages` (liste de pages PDF).
    Si `pages` est fourni, l'étape 7 est appliquée AVANT les autres étapes
    pour détecter en-têtes/pieds récurrents avec les frontières de pages.

    `pipeline` (optionnel) : `Pipeline` custom (cf `cleaners.steps`) pour
    activer/désactiver/réordonner des étapes. Si `None`, utilise
    `default_pipeline(aggressive=aggressive)`.

    `metrics_sink` (optionnel) : liste appendable où les `StepMetrics` produits
    par `Pipeline.run()` sont étendus. Permet à `core.process` (et au flag CLI
    `--profile`) de collecter les métriques par étape sans modifier la valeur
    de retour publique. `None` = pas de collecte (coût ~0).
    """
    from trimtokens.cleaners.steps import default_pipeline

    if text is None and pages is None:
        raise ValueError("Fournir `text` ou `pages`.")
    if text is not None and pages is not None:
        raise ValueError("Fournir `text` OU `pages`, pas les deux.")

    if pages is not None:
        original_text = "\n\n".join(pages)
        original_chars = len(original_text)
        cleaned_pages = strip_recurring_headers_footers(pages)
        working = "\n\n".join(cleaned_pages)
    else:
        assert text is not None
        original_text = text
        original_chars = len(text)
        working = text

    pipe = pipeline if pipeline is not None else default_pipeline(aggressive=aggressive)
    working, metrics = pipe.run(working)

    if metrics_sink is not None:
        metrics_sink.extend(metrics)

    stats = compute_stats(
        original_size_bytes=original_size_bytes,
        original_chars=original_chars,
        cleaned_text=working,
        original_text=original_text,
    )
    return working, stats
