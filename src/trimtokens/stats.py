"""Estimation de tokens et calcul des statistiques de nettoyage."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from trimtokens.models import CleanStats


@lru_cache(maxsize=1)
def _get_encoder() -> Any | None:
    """Charge l'encodeur tiktoken cl100k_base ; retourne None si indisponible."""
    try:
        import tiktoken

        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def estimate_tokens(text: str) -> int:
    """Estime le nombre de tokens.

    Utilise `tiktoken` avec l'encodage `cl100k_base` si disponible,
    sinon fallback heuristique `len(text) // 4`.
    """
    if not text:
        return 0
    encoder = _get_encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    return max(1, len(text) // 4)


def compute_stats(
    original_size_bytes: int,
    original_chars: int,
    cleaned_text: str,
    original_text: str | None = None,
) -> CleanStats:
    """Construit un CleanStats à partir du texte nettoyé et des compteurs initiaux."""
    cleaned_size_bytes = len(cleaned_text.encode("utf-8"))
    cleaned_chars = len(cleaned_text)
    tokens_cleaned = estimate_tokens(cleaned_text)
    if original_text is not None:
        tokens_original = estimate_tokens(original_text)
    elif original_chars > 0:
        tokens_original = max(1, original_chars // 4)
    else:
        tokens_original = 0

    # Tokens "input" = ce que Claude facturerait si on uploadait le fichier brut.
    # Approximation standard ~ 1 token / 4 bytes (cohérente avec trimtokens.com).
    tokens_input = max(0, original_size_bytes // 4)

    return CleanStats(
        original_size_bytes=original_size_bytes,
        cleaned_size_bytes=cleaned_size_bytes,
        original_chars=original_chars,
        cleaned_chars=cleaned_chars,
        tokens_estimated=tokens_cleaned,
        tokens_original_estimated=tokens_original,
        tokens_input_estimated=tokens_input,
    )
