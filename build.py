"""Build standalone executables via PyInstaller pour TrimTokens.

Produit deux binaires par OS :
- `trimtokens-{os}-{arch}` (CLI)
- `trimtokens-gui-{os}-{arch}` (GUI)

Usage :
    python build.py                  # CLI + GUI pour l'OS courant
    python build.py --cli-only       # CLI uniquement
    python build.py --gui-only       # GUI uniquement
    python build.py --clean          # Nettoie build/ et dist/ avant
    python build.py --debug          # Build console (visible) pour GUI (debug imports)

Tesseract reste une dépendance système externe : trop lourd à embarquer (~50 Mo
par langue). Le binaire détecte son absence et affiche les instructions d'installation.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
BUILD = ROOT / "build"


# Hidden imports nécessaires pour que PyInstaller embarque tout ce que le code
# importe dynamiquement (importlib.import_module dans core.py, deps optionnelles).
HIDDEN_IMPORTS_BASE = [
    # Core deps
    "PIL",
    "PIL._tkinter_finder",
    "fitz",
    "openpyxl",
    "docx",
    "pptx",
    "bs4",
    "markdownify",
    "striprtf",
    "striprtf.striprtf",
    "chardet",
    "pyperclip",
    "yaml",
    # tiktoken et extensions (téléchargements à runtime parfois)
    "tiktoken",
    "tiktoken_ext",
    "tiktoken_ext.openai_public",
    # OCR
    "pytesseract",
    "cv2",
    # Extracteurs dispatchés dynamiquement par core._resolve_extractor
    "trimtokens.extractors.pdf",
    "trimtokens.extractors.docx",
    "trimtokens.extractors.pptx",
    "trimtokens.extractors.xlsx_csv",
    "trimtokens.extractors.html",
    "trimtokens.extractors.txt_md",
    "trimtokens.extractors.rtf",
    "trimtokens.extractors.image",
]

HIDDEN_IMPORTS_GUI = [
    "tkinterdnd2",
    "customtkinter",
    "darkdetect",
    "tkinter",
    "tkinter.filedialog",
    "tkinter.ttk",
]


def detect_platform() -> tuple[str, str]:
    """Retourne (os_name, arch) pour le suffixe binaire.

    os_name : windows | macos | linux
    arch    : x64 | arm64
    """
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "darwin":
        os_name = "macos"
        arch = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    elif system == "windows":
        os_name = "windows"
        arch = "x64" if machine in {"amd64", "x86_64"} else machine
    elif system == "linux":
        os_name = "linux"
        arch = "x64" if machine in {"x86_64", "amd64"} else machine
    else:
        os_name = system
        arch = machine
    return os_name, arch


def collect_data_args() -> list[str]:
    """Retourne les --add-data PyInstaller pour ressources non-Python (tcl tkdnd, thèmes ctk)."""
    args: list[str] = []
    sep = ";" if platform.system() == "Windows" else ":"

    try:
        import tkinterdnd2  # type: ignore[import-not-found]

        tkdnd_root = Path(tkinterdnd2.__file__).parent
        # Le dossier `tkdnd` contient les libs natives (.dll, .so, .dylib) + .tcl
        tkdnd_dir = tkdnd_root / "tkdnd"
        if tkdnd_dir.exists():
            args.extend(["--add-data", f"{tkdnd_dir}{sep}tkinterdnd2/tkdnd"])
    except ImportError:
        print("WARNING : tkinterdnd2 introuvable — drag&drop GUI ne fonctionnera pas")

    try:
        import customtkinter  # type: ignore[import-not-found]

        ctk_root = Path(customtkinter.__file__).parent
        if ctk_root.exists():
            args.extend(["--add-data", f"{ctk_root}{sep}customtkinter"])
    except ImportError:
        print("WARNING : customtkinter introuvable — GUI ne fonctionnera pas")

    return args


def base_pyinstaller_cmd(name: str, clean: bool) -> list[str]:
    cmd: list[str] = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        name,
        "--onefile",
        "--noconfirm",
        "--paths",
        str(SRC),
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD),
        "--specpath",
        str(BUILD),
    ]
    if clean:
        cmd.append("--clean")
    return cmd


def build_cli(os_name: str, arch: str, clean: bool) -> Path:
    """Build CLI executable."""
    name = f"trimtokens-{os_name}-{arch}"

    cmd = base_pyinstaller_cmd(name, clean)
    cmd.append("--console")

    for module in HIDDEN_IMPORTS_BASE:
        cmd.extend(["--hidden-import", module])

    entry = SRC / "trimtokens" / "cli.py"
    cmd.append(str(entry))

    print(f"\n=== Build CLI : {name} ===")
    print(" ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    suffix = ".exe" if os_name == "windows" else ""
    return DIST / f"{name}{suffix}"


def build_gui(os_name: str, arch: str, clean: bool, debug: bool = False) -> Path:
    """Build GUI executable."""
    name = f"trimtokens-gui-{os_name}-{arch}"

    cmd = base_pyinstaller_cmd(name, clean)
    if debug:
        cmd.append("--console")
    elif os_name == "linux":
        cmd.append("--console")  # Linux : pas de --windowed (xterm peut afficher logs)
    else:
        cmd.append("--windowed")

    for module in HIDDEN_IMPORTS_BASE + HIDDEN_IMPORTS_GUI:
        cmd.extend(["--hidden-import", module])

    for data_arg in collect_data_args():
        cmd.append(data_arg)

    # Collect submodules dynamiques de customtkinter (thèmes JSON, assets)
    cmd.extend(["--collect-all", "customtkinter"])

    entry = SRC / "trimtokens" / "gui.py"
    cmd.append(str(entry))

    print(f"\n=== Build GUI : {name} ===")
    print(" ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    suffix = ".exe" if os_name == "windows" else ""
    return DIST / f"{name}{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build TrimTokens executables via PyInstaller")
    parser.add_argument("--cli-only", action="store_true", help="Construire uniquement la CLI")
    parser.add_argument("--gui-only", action="store_true", help="Construire uniquement la GUI")
    parser.add_argument("--clean", action="store_true", help="Nettoyer build/ et dist/ avant")
    parser.add_argument("--debug", action="store_true", help="Build GUI en mode console (debug)")
    args = parser.parse_args()

    if args.cli_only and args.gui_only:
        parser.error("--cli-only et --gui-only sont mutuellement exclusifs")

    os_name, arch = detect_platform()
    print(f"Target : {os_name}-{arch}")
    print(f"Python : {sys.version}")

    if args.clean:
        for d in (DIST, BUILD):
            if d.exists():
                print(f"Nettoyage de {d}")
                shutil.rmtree(d)

    outputs: list[Path] = []

    if not args.gui_only:
        outputs.append(build_cli(os_name, arch, args.clean))

    if not args.cli_only:
        outputs.append(build_gui(os_name, arch, args.clean, debug=args.debug))

    print("\n=== Build terminé ===")
    for path in outputs:
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            print(f"  ✓ {path}  ({size_mb:.1f} Mo)")
        else:
            print(f"  ✗ {path}  (fichier introuvable !)")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
