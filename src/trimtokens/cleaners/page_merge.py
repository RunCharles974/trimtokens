"""Fusion paragraphes inter-pages.

Heuristique : quand une page se termine sans ponctuation finale (`.!?:;`) et que
la page suivante commence par une minuscule (ou un caractère continuant le texte),
on considère que le paragraphe s'étend sur 2 pages. On marque alors la page
suivante comme "continuation" pour que le renderer omette son header `## Page N`.

Pas de fusion physique des sections (on garde la trace de l'index original), juste
un flag dans `Section.metadata["continuation"]` que le renderer consomme.
"""

from __future__ import annotations

import re

# Termine sans ponctuation finale (ignore espaces et fin de ligne)
_SENTENCE_END_RE = re.compile(r"[.!?:;»\")\]]\s*$")
# Préfixe optionnel : numéro de page éventuellement répété en début de page
# (ex. "5 principale vertu..."). On l'ignore avant de tester la suite.
_LEADING_PAGE_NUM_RE = re.compile(r"^\s*\d{1,4}\s+")
# Commence par minuscule ou par un caractère qui n'est ni titre ni liste
_CONTINUATION_START_RE = re.compile(r"^\s*[a-zàâäçéèêëîïôöùûüÿ,;\-)\]]")


def is_continuation(prev_text: str, next_text: str) -> bool:
    """True si `next_text` continue le paragraphe de `prev_text`."""
    if not prev_text.strip() or not next_text.strip():
        return False
    if _SENTENCE_END_RE.search(prev_text.rstrip()):
        return False
    # Ignorer un éventuel numéro de page en tête (ex. "5 principale...")
    stripped = _LEADING_PAGE_NUM_RE.sub("", next_text, count=1)
    if not _CONTINUATION_START_RE.match(stripped):
        return False
    return True


def mark_continuations(pages: list[str]) -> list[bool]:
    """Pour chaque page, retourne True si c'est une continuation de la précédente.

    Page 0 toujours False. Page N (N≥1) True ssi pages[N-1] termine sans
    ponctuation finale et pages[N] commence en minuscule.
    """
    flags = [False] * len(pages)
    for i in range(1, len(pages)):
        flags[i] = is_continuation(pages[i - 1], pages[i])
    return flags
