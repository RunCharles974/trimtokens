"""Moteur OCR Tesseract via pytesseract.

Fallback gracieux si Tesseract introuvable : `is_tesseract_available()` retourne False
et l'appelant continue sans OCR (texte natif extractible conservé).
"""

from __future__ import annotations

import logging
import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

log = logging.getLogger(__name__)


# Chemins d'installation classiques de Tesseract sous Windows (vérifiés si PATH
# ne contient pas tesseract — utile quand l'utilisateur vient d'installer mais
# que la session courante n'a pas rafraîchi PATH).
_WINDOWS_FALLBACK_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Tesseract-OCR\tesseract.exe",
)


def _try_configure_tesseract_path() -> str | None:
    """Cherche un binaire tesseract et configure pytesseract.tesseract_cmd.

    Ordre : variable d'env `TESSERACT_CMD`, PATH système, chemins Windows usuels.
    Retourne le chemin trouvé ou None.
    """
    env_path = os.environ.get("TESSERACT_CMD")
    if env_path and Path(env_path).is_file():
        return env_path

    on_path = shutil.which("tesseract")
    if on_path:
        return on_path

    if os.name == "nt":
        for candidate in _WINDOWS_FALLBACK_PATHS:
            if Path(candidate).is_file():
                return candidate

    return None


def _try_configure_tessdata_dir() -> str | None:
    """Détermine un répertoire tessdata utilisable et l'expose via `TESSDATA_PREFIX`.

    Ordre :
    1. Variable d'env `TESSDATA_PREFIX` déjà définie → laisser tel quel
    2. Dossier `tessdata/` à la racine du projet (cwd)
    3. Dossier `~/.trimtokens/tessdata/`
    4. Aucun (utilise le tessdata par défaut de l'install Tesseract)
    """
    if os.environ.get("TESSDATA_PREFIX"):
        return os.environ["TESSDATA_PREFIX"]

    candidates = [
        Path.cwd() / "tessdata",
        Path.home() / ".trimtokens" / "tessdata",
    ]
    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("*.traineddata")):
            os.environ["TESSDATA_PREFIX"] = str(candidate)
            log.debug("TESSDATA_PREFIX configuré sur %s", candidate)
            return str(candidate)

    return None


@lru_cache(maxsize=1)
def is_tesseract_available() -> bool:
    """Vérifie si Tesseract est installé et accessible.

    Résultat mis en cache (lru_cache) pour éviter de re-tester à chaque page.
    Configure automatiquement `pytesseract.tesseract_cmd` si le binaire est
    trouvé hors du PATH (ex : install récente sans rafraîchissement de session).
    """
    try:
        import pytesseract  # type: ignore[import-untyped]

        binary_path = _try_configure_tesseract_path()
        if binary_path is not None:
            pytesseract.pytesseract.tesseract_cmd = binary_path

        _try_configure_tessdata_dir()

        pytesseract.get_tesseract_version()
        return True
    except Exception as exc:
        log.debug("Tesseract indisponible : %s", exc)
        return False


def get_tesseract_install_hint() -> str:
    """Instructions d'installation par OS."""
    return (
        "Installation Tesseract :\n"
        "  Windows : winget install --id UB-Mannheim.TesseractOCR\n"
        "            ou  choco install tesseract\n"
        "  macOS   : brew install tesseract tesseract-lang\n"
        "  Linux   : sudo apt install tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng"
    )


def detect_orientation(image: PILImage) -> int:
    """Détecte l'angle de rotation via Tesseract OSD.

    Retourne le nombre de degrés à appliquer pour redresser (0/90/180/270).
    Retourne 0 si l'OSD échoue.
    """
    try:
        import pytesseract  # type: ignore[import-untyped]

        osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
        rotate_value = osd.get("rotate", 0)
        return int(rotate_value)
    except Exception as exc:
        log.debug("OSD orientation détection échouée : %s", exc)
        return 0


def ocr_pil_image(
    image: PILImage,
    languages: str = "fra+eng",
    psm: int = 6,
) -> str:
    """OCR sur un objet PIL Image déjà préprocessé. Retourne le texte brut."""
    if not is_tesseract_available():
        return ""
    try:
        import pytesseract  # type: ignore[import-untyped]

        config = f"--oem 3 --psm {psm}"
        return pytesseract.image_to_string(image, lang=languages, config=config)
    except Exception as exc:
        log.warning("OCR Tesseract échoué : %s", exc)
        return ""


def ocr_file(path: Path, languages: str = "fra+eng", psm: int = 6) -> str:
    """OCR sur un fichier image (PNG/JPG/etc) via path."""
    from PIL import Image

    with Image.open(path) as image:
        return ocr_pil_image(image, languages=languages, psm=psm)
