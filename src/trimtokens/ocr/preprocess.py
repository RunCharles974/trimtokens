"""Préprocessing d'image pour OCR (Pillow + opencv-python-headless).

Pipeline (cf TrimTokens.md §2) :
1. Conversion grayscale (mode "L")
2. Auto-rotation via Tesseract OSD (quadrants 90/180/270)
3. Deskew fin (correction inclinaison < 90°) via Hough/minAreaRect
4. Upscale si DPI < min_dpi (x2 ou x3 selon DPI initial)
5. Égalisation contraste CLAHE (Contrast Limited Adaptive Histogram Equalization)
6. Binarisation Otsu (opencv si dispo, sinon seuillage Pillow)
7. Débruitage léger (median blur opencv si dispo)
8. Crop bordures noires si détectées

Chaque étape est dégradable indépendamment : si opencv n'est pas installé,
on saute simplement les étapes dépendant de cv2 et on garde les fallbacks Pillow.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

log = logging.getLogger(__name__)

MIN_DPI = 300
DEFAULT_BORDER_THRESHOLD = 50  # luminance moyenne sous laquelle on considère "bordure noire"


def preprocess(image: PILImage, min_dpi: int = MIN_DPI) -> PILImage:
    """Pipeline complet : grayscale → rotation → deskew → upscale → CLAHE → binarisation → denoise → crop."""
    image = to_grayscale(image)
    image = auto_rotate(image)
    image = deskew(image)
    image = upscale_if_needed(image, min_dpi=min_dpi)
    image = enhance_contrast(image)
    image = binarize(image)
    image = denoise(image)
    image = crop_borders(image)
    return image


def to_grayscale(image: PILImage) -> PILImage:
    """Étape 1 : conversion en niveaux de gris (mode L)."""
    if image.mode == "L":
        return image
    return image.convert("L")


def auto_rotate(image: PILImage) -> PILImage:
    """Étape 2 : auto-rotation via Tesseract OSD."""
    from trimtokens.ocr.engine import detect_orientation

    angle = detect_orientation(image)
    if angle and angle % 360 != 0:
        # PIL rotate avec valeur négative pour redresser
        return image.rotate(-angle, expand=True, fillcolor=255)
    return image


def upscale_if_needed(image: PILImage, min_dpi: int = MIN_DPI) -> PILImage:
    """Étape 3 : upscale x2 si DPI < min_dpi, x3 si très bas."""
    dpi_info = image.info.get("dpi")
    dpi = dpi_info[0] if isinstance(dpi_info, tuple) and dpi_info else 72

    if dpi >= min_dpi:
        return image

    factor = 3 if dpi < 100 else 2
    new_size = (image.width * factor, image.height * factor)

    from PIL import Image as PILImageModule

    return image.resize(new_size, PILImageModule.LANCZOS)


def deskew(image: PILImage, max_angle: float = 10.0) -> PILImage:
    """Étape 3 : correction d'inclinaison fine (< max_angle degrés).

    Détecte l'angle dominant via les pixels foncés (texte) puis rotate. No-op
    si opencv absent ou si angle estimé proche de 0.
    """
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np
        from PIL import Image as PILImageModule

        arr = np.array(image)
        if arr.ndim != 2:
            return image

        # Inverse (texte = blanc) puis seuil pour isoler les caractères
        inv = cv2.bitwise_not(arr)
        _, threshed = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        coords = np.column_stack(np.where(threshed > 0))
        if coords.size < 100:
            return image

        # minAreaRect retourne un angle dans [-90, 0)
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        # On corrige uniquement les petites inclinaisons (sinon OSD a déjà tourné)
        if abs(angle) < 0.3 or abs(angle) > max_angle:
            return image

        (h, w) = arr.shape[:2]
        center = (w // 2, h // 2)
        rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            arr,
            rot_mat,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return PILImageModule.fromarray(rotated)
    except Exception as exc:
        log.debug("Deskew échoué : %s", exc)
        return image


def enhance_contrast(image: PILImage, clip_limit: float = 2.0, tile_grid: int = 8) -> PILImage:
    """Étape 5 : égalisation locale de contraste via CLAHE.

    Améliore lisibilité des scans pâles ou jaunis sans cramer les noirs. No-op
    si opencv absent.
    """
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np
        from PIL import Image as PILImageModule

        arr = np.array(image)
        if arr.ndim != 2:
            return image
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_grid, tile_grid))
        enhanced = clahe.apply(arr)
        return PILImageModule.fromarray(enhanced)
    except Exception as exc:
        log.debug("CLAHE indisponible : %s", exc)
        return image


def binarize(image: PILImage) -> PILImage:
    """Étape 4 : binarisation Otsu (opencv) ou seuillage simple (Pillow fallback)."""
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np
        from PIL import Image as PILImageModule

        arr = np.array(image)
        _, binary = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return PILImageModule.fromarray(binary)
    except Exception as exc:
        log.debug("Binarisation opencv échouée, fallback Pillow : %s", exc)
        return image.point(lambda p: 255 if p > 128 else 0, mode="L")


def denoise(image: PILImage) -> PILImage:
    """Étape 5 : débruitage léger via opencv median blur (no-op si opencv absent)."""
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np
        from PIL import Image as PILImageModule

        arr = np.array(image)
        denoised = cv2.medianBlur(arr, 3)
        return PILImageModule.fromarray(denoised)
    except Exception as exc:
        log.debug("Denoise opencv indisponible : %s", exc)
        return image


def crop_borders(
    image: PILImage,
    min_border_px: int = 10,
    threshold: int = DEFAULT_BORDER_THRESHOLD,
) -> PILImage:
    """Étape 6 : crop des bordures noires si détectées (≥ min_border_px épaisses).

    Conservatif : ne crop que si chaque côté a une bordure noire détectée d'au moins
    `min_border_px` pixels d'épaisseur (luminance moyenne < threshold).
    """
    try:
        import numpy as np
        from PIL import Image as PILImageModule

        arr = np.array(image)
        if arr.ndim != 2:
            return image

        height, width = arr.shape
        if height < 3 * min_border_px or width < 3 * min_border_px:
            return image

        row_means = arr.mean(axis=1)
        col_means = arr.mean(axis=0)

        top = _first_above(row_means, threshold, 0)
        bottom = _first_above(row_means[::-1], threshold, 0)
        left = _first_above(col_means, threshold, 0)
        right = _first_above(col_means[::-1], threshold, 0)

        # Crop uniquement si bordure détectée >= seuil
        if (
            top < min_border_px
            and bottom < min_border_px
            and left < min_border_px
            and right < min_border_px
        ):
            return image

        y0 = top
        y1 = height - bottom
        x0 = left
        x1 = width - right

        if y1 <= y0 or x1 <= x0:
            return image

        cropped = arr[y0:y1, x0:x1]
        return PILImageModule.fromarray(cropped)
    except Exception as exc:
        log.debug("Crop bordures échoué : %s", exc)
        return image


def _first_above(arr, threshold: float, default: int) -> int:
    """Retourne l'index du premier élément >= threshold, sinon default."""
    for i, v in enumerate(arr):
        if v >= threshold:
            return i
    return default
