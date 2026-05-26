"""Tests du module page_merge : détection continuations inter-pages."""

from __future__ import annotations

from trimtokens.cleaners.page_merge import is_continuation, mark_continuations


def test_continuation_basic_lowercase() -> None:
    prev = "Cette phrase se poursuit sur la"
    nxt = "page suivante avec la suite."
    assert is_continuation(prev, nxt)


def test_no_continuation_after_period() -> None:
    prev = "Fin de la phrase."
    nxt = "nouvelle phrase qui commence."
    assert not is_continuation(prev, nxt)


def test_no_continuation_after_question() -> None:
    prev = "Est-ce vraiment terminé ?"
    nxt = "oui c'est fini."
    assert not is_continuation(prev, nxt)


def test_no_continuation_capital_start() -> None:
    prev = "Sans ponctuation finale"
    nxt = "Mais commence par majuscule"
    assert not is_continuation(prev, nxt)


def test_continuation_ignores_leading_page_number() -> None:
    """Numéro de page en début (ex '5 principale') doit être ignoré."""
    prev = "les jardins créoles ont pour"
    nxt = "5 principale vertu de faire la part belle"
    assert is_continuation(prev, nxt)


def test_no_continuation_empty_strings() -> None:
    assert not is_continuation("", "lowercase start")
    assert not is_continuation("no ending", "")


def test_continuation_with_comma_start() -> None:
    prev = "Liste d'éléments suivants"
    nxt = ", et la suite avec une virgule"
    assert is_continuation(prev, nxt)


def test_mark_continuations_first_page_never_flagged() -> None:
    pages = ["sans ponctuation", "continuation possible"]
    flags = mark_continuations(pages)
    assert flags[0] is False


def test_mark_continuations_full_sequence() -> None:
    pages = [
        "Première page ouverte sur la",
        "deuxième page sans capital. Fin.",
        "Troisième page commence en majuscule",
        "Quatrième commence aussi en majuscule.",
    ]
    flags = mark_continuations(pages)
    # [1] continue [0] (lowercase 'deuxième' après "la")
    # [2] ne continue pas [1] (point final)
    # [3] commence par majuscule donc pas une continuation
    assert flags == [False, True, False, False]
