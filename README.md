# TrimTokens

> **Allégez vos documents pour l'IA, en local.**
> *Lighten your docs locally, AI-ready.*

Convertit n'importe quel document (PDF, DOCX, PPTX, XLSX, images, HTML…) en **Markdown propre, compact et prêt à coller dans Claude**, pour réduire massivement la consommation de tokens. **100 % local, zéro upload.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## Pourquoi

Les documents bruts envoyés à Claude (et autres LLM) contiennent énormément de bruit :
- métadonnées XML inutiles (PPTX/DOCX/XLSX = ZIP de XML très verbeux),
- en-têtes / pieds de page répétés sur chaque page,
- espaces multiples, tabulations, caractères Unicode parasites (zero-width, BOM, soft hyphens…),
- doublons, mentions légales, boilerplate,
- images encodées en base64 qui n'apportent rien au texte.

**TrimTokens élimine tout ce bruit avant l'envoi à un LLM.** Objectif chiffré : **60 à 90 % de réduction des tokens** sans perte d'information sémantique.

### Exemple de gains observés

| Type de document | Taille avant | Tokens avant | Tokens après | Gain |
|---|---|---|---|---|
| PDF technique 50 pages | 2.4 MB | ~78 000 | ~10 300 | **-87 %** |
| Présentation PPTX 30 slides | 4.1 MB | ~42 000 | ~6 800 | **-84 %** |
| Tableur XLSX 5 feuilles | 1.8 MB | ~35 000 | ~12 100 | **-65 %** |
| Document DOCX 80 pages | 850 KB | ~95 000 | ~28 500 | **-70 %** |
| Image scannée (OCR) | 3.2 MB | — | ~2 400 | — |

---

## Caractéristiques

- 🔒 **100 % local** — aucun appel réseau, aucune fuite de données
- 🖥️ **Multi-plateforme** — Windows, macOS, Linux
- 📦 **Portable** — installable via pip, pipx ou en exécutable standalone
- 🎨 **CLI et GUI** — drag & drop natif depuis l'explorateur
- 🔍 **OCR intégré** — Tesseract avec préprocessing OpenCV (rotation, binarisation Otsu, débruitage)
- ⚡ **Cache OCR** — SHA-256 par fichier+paramètres, jamais de double OCR
- 🧠 **Pipeline en 11 étapes** — Unicode NFKC, ligatures, recollage hyphens, dédup paragraphes, suppression headers récurrents…
- 📊 **Stats détaillées** — réduction bytes / caractères / tokens estimés (via tiktoken)

---

## Formats supportés

| Catégorie | Extensions |
|---|---|
| Documents | `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.csv`, `.rtf` |
| Texte | `.txt`, `.md`, `.markdown` |
| Web | `.html`, `.htm` |
| Images | `.png`, `.jpg`, `.jpeg`, `.webp`, `.tiff`, `.tif`, `.bmp`, `.heic`, `.heif` |

---

## Installation

### Mode 1 — pip (développeurs)

```bash
pip install trimtokens[ocr,gui]
```

Variantes :
- `pip install trimtokens` — CLI uniquement, sans OCR ni GUI
- `pip install trimtokens[ocr]` — CLI + OCR
- `pip install trimtokens[gui]` — CLI + GUI
- `pip install trimtokens[ocr,gui]` — tout

### Mode 2 — pipx (utilisateurs avancés, isolement)

```bash
pipx install "trimtokens[ocr,gui]"
```

### Mode 3 — Exécutable standalone (utilisateurs sans Python) ⭐

Télécharger le binaire pour votre OS depuis la [page Releases GitHub](https://github.com/cg97411/trimtokens/releases/latest) :

| OS | Architecture | CLI | GUI |
|---|---|---|---|
| Windows | x64 | `trimtokens-windows-x64.exe` | `trimtokens-gui-windows-x64.exe` |
| macOS | Intel | `trimtokens-macos-x64` | `trimtokens-gui-macos-x64` |
| macOS | Apple Silicon | `trimtokens-macos-arm64` | `trimtokens-gui-macos-arm64` |
| Linux | x64 | `trimtokens-linux-x64` | `trimtokens-gui-linux-x64` |

**macOS / Linux** — rendre exécutable :
```bash
chmod +x trimtokens-macos-arm64
```

**macOS Gatekeeper** — si le binaire est bloqué :
```bash
xattr -d com.apple.quarantine trimtokens-macos-arm64
```

---

## Installer Tesseract (pour OCR)

Tesseract reste une dépendance système externe (trop volumineuse à embarquer). TrimTokens fonctionne sans Tesseract, mais l'OCR sera désactivé.

### Windows

```powershell
winget install --id UB-Mannheim.TesseractOCR
# OU
choco install tesseract
```

Vérifier l'installation : `tesseract --version`. Si non trouvé, ajouter `C:\Program Files\Tesseract-OCR\` à votre PATH.

### macOS

```bash
brew install tesseract tesseract-lang
```

### Linux (Debian / Ubuntu)

```bash
sudo apt update
sudo apt install tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng
```

### Linux (Fedora / RHEL)

```bash
sudo dnf install tesseract tesseract-langpack-fra tesseract-langpack-eng
```

---

## Utilisation CLI

```bash
# Le plus simple : un fichier → un .clean.md à côté
trimtokens document.pdf

# Dossier entier en récursif, sortie vers ./clean/
trimtokens ./dossier/ --recursive --out ./clean/

# Stdout (pour pipe vers un autre outil)
trimtokens document.pdf --stdout

# Copier directement dans le presse-papiers
trimtokens document.pdf --clipboard

# Mode agressif (dédup à partir de 2 occurrences au lieu de 3)
trimtokens document.pdf --aggressive

# Forcer OCR même si texte natif présent
trimtokens scan.pdf --force-ocr

# Désactiver OCR (utile si Tesseract pas installé)
trimtokens document.pdf --no-ocr

# Format JSON pour usage programmatique
trimtokens document.pdf --format json

# Langues OCR spécifiques
trimtokens document.pdf --ocr-lang deu+eng

# Mode silencieux (sans table de stats)
trimtokens document.pdf --quiet

# Limite la sortie à 50 000 caractères
trimtokens document.pdf --max-chars 50000
```

### Sortie console (Rich)

```
✓ document.pdf → document.clean.md
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┓
┃ Métrique       ┃    Avant ┃    Après ┃    Gain ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━┩
│ Taille         │   2.4 MB │    18 KB │   -99 % │
│ Caractères     │  312 450 │   41 220 │   -87 % │
│ Tokens estimés │  ~78 000 │  ~10 300 │   -87 % │
│ OCR            │ 3 page(s)│        — │       — │
│ Durée          │        — │    4.20s │       — │
└────────────────┴──────────┴──────────┴─────────┘
```

### Tous les flags CLI

```
trimtokens --help
```

| Flag | Court | Défaut | Description |
|---|---|---|---|
| `--format` | `-f` | `md` | Format de sortie : `md`, `txt`, `json` |
| `--out` | `-o` | `.` | Dossier de sortie |
| `--stdout` | | | Écrire sur stdout au lieu d'un fichier |
| `--clipboard` | `-c` | | Copier dans le presse-papiers |
| `--recursive` | `-r` | | Récursif pour les dossiers |
| `--ocr-lang` | | `fra+eng` | Langues OCR (codes Tesseract) |
| `--no-ocr` | | | Désactiver OCR |
| `--force-ocr` | | | Forcer OCR même si texte natif présent |
| `--ocr-psm` | | `6` | Tesseract PSM (1, 6, 11) |
| `--max-chars` | | `0` | Tronquer à N caractères (0 = pas de limite) |
| `--aggressive` | `-a` | | Déduplication à 2 occurrences |
| `--no-cache` | | | Ignorer le cache OCR |
| `--workers` | `-w` | `0` | Workers OCR parallèles (0 = auto) |
| `--quiet` | `-q` | | Pas de table de stats |
| `--verbose` | `-v` | | Logs DEBUG |
| `--version` | | | Affiche la version |

---

## Utilisation GUI

```bash
trimtokens-gui
```

Interface drag & drop multi-plateforme :

```
┌──────────────────────────────────────────────────┐
│              TrimTokens                         │
│      Documents → Markdown compact pour LLM       │
├──────────────────────────────────────────────────┤
│                                                  │
│        📂  Glissez vos fichiers ici              │
│        (ou cliquez pour parcourir)               │
│                                                  │
├──────────────────────────────────────────────────┤
│ Langues OCR : [✓]FR [✓]EN [ ]DE [ ]ES [ ]IT     │
│ [ ] Mode agressif  [ ] Forcer OCR                │
│ [ ] Presse-papiers [ ] Ouvrir après              │
├──────────────────────────────────────────────────┤
│ [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░] 75%                       │
│ Traitement : photo.jpg (3/4)                     │
├──────────────────────────────────────────────────┤
│ Journal                                          │
│ ✓ doc.pdf → doc.clean.md (-87% taille)          │
│ ✓ note.docx → note.clean.md (-65%)              │
│ ⟳ photo.jpg ...                                  │
├──────────────────────────────────────────────────┤
│  3/4 fichiers — 5.2 MB → 142 KB (-97%)           │
│                  [📁 Ouvrir dossier de sortie]   │
└──────────────────────────────────────────────────┘
```

### Lancer la GUI au démarrage / via raccourci

**Windows** : créer un raccourci sur le bureau pointant vers `trimtokens-gui-windows-x64.exe`.

**macOS** : `.app` bundle généré par PyInstaller (drag dans `/Applications/`).

**Linux** : ajouter un fichier `.desktop` dans `~/.local/share/applications/` :
```ini
[Desktop Entry]
Name=TrimTokens
Exec=/usr/local/bin/trimtokens-gui-linux-x64
Type=Application
Categories=Utility;
```

---

## Format de sortie

### Markdown avec front-matter YAML

```markdown
---
source: document.pdf
type: pdf
extracted_at: '2026-05-25T14:32:00Z'
ocr_used: true
ocr_pages: [3, 7, 12]
language: fra+eng
stats:
  original_size_bytes: 2516582
  cleaned_size_bytes: 18432
  reduction_percent: 99.27
  original_chars: 312450
  cleaned_chars: 41220
  tokens_estimated: 10300
  tokens_original_estimated: 78000
  tokens_reduction_percent: 86.79
---

# Titre du document

## Page 1

Contenu textuel propre...

## Page 2

...

## Page 3 (OCR)

Contenu issu de l'OCR de la page scannée.
```

### Structure par format

| Format source | Structure du Markdown produit |
|---|---|
| **PDF** | Un `## Page N` par page ; pages OCR marquées `## Page N (OCR)` |
| **DOCX** | Préserve les `Heading 1..6` natifs comme `#`..`######` + listes |
| **PPTX** | Un `## Slide N — Titre` par slide + `### Notes du présentateur` |
| **XLSX/CSV** | Un `## Feuille : Nom` par feuille + table Markdown |
| **HTML** | Conversion via markdownify (strip script/style/head) |
| **Images** | `## Texte extrait (OCR)` + contenu brut |

---

## Pipeline de nettoyage

11 étapes appliquées dans l'ordre :

1. **Normalisation Unicode** (NFKC)
2. **Suppression caractères invisibles** : zero-width (U+200B/C/D), BOM (U+FEFF), soft hyphen (U+00AD), caractères de contrôle non imprimables
3. **Conversion ligatures typographiques** : `ﬁ`→`fi`, `ﬂ`→`fl`, `ﬀ`→`ff`, `ﬃ`→`ffi`, `ﬄ`→`ffl`
4. **Recollage mots coupés en fin de ligne** : `exem-\nple` → `exemple`
5. **Espaces multiples / tabulations** → un seul espace
6. **Sauts de ligne consécutifs** → maximum 2
7. **Suppression en-têtes/pieds de page récurrents** : ligne apparaissant sur ≥ 30 % des pages ou pattern `Page N`
8. **Déduplication paragraphes** identiques (≥ 3 occurrences, ou ≥ 2 en mode agressif)
9. **Suppression lignes ponctuation/séparateurs** seules (`---`, `***`, `???`)
10. **Trim final** + normalisation EOL → `\n`
11. **Estimation tokens** via `tiktoken` (`cl100k_base`) avec fallback `len/4`

---

## OCR — détails

### Heuristique de déclenchement

- **PDF** : OCR uniquement sur les pages avec **< 50 caractères extractibles** natifs (n'OCR jamais l'ensemble d'un PDF si seules quelques pages sont scannées)
- **Image** : OCR systématique
- **`--force-ocr`** : OCR sur toutes les pages
- **`--no-ocr`** : aucun OCR

### Préprocessing (Pillow + OpenCV)

1. Conversion en niveaux de gris
2. Auto-rotation via Tesseract OSD
3. Upscale x2 ou x3 si DPI < 300
4. Binarisation Otsu (OpenCV) ou seuillage Pillow en fallback
5. Débruitage median blur
6. Crop bordures noires (conservatif, ≥ 10 px d'épaisseur détectés)

### Cache

Clé SHA-256(fichier + langues + PSM). Stockage :
- Linux / macOS : `~/.trimtokens/cache/ocr/`
- Windows : `%APPDATA%\trimtokens\cache\ocr\`
- Override : variable d'environnement `TRIMTOKENS_HOME`

---

## Configuration utilisateur

Fichier optionnel `~/.trimtokens/config.toml` (ou `%APPDATA%\trimtokens\config.toml` sous Windows). Voir [`config.example.toml`](config.example.toml) pour la référence complète.

---

## Limitations connues

- **Tesseract** est une dépendance système — pas embarqué dans les binaires standalone (trop lourd, ~50 Mo par langue). Sans Tesseract, l'OCR est désactivé silencieusement (warning + texte natif conservé).
- **PDF chiffrés** ne sont pas supportés actuellement.
- **Tables PDF complexes** (cellules fusionnées, multi-niveau) : extraction texte par flux, pas de reconstruction tabulaire.
- **HEIC/HEIF** nécessitent `pip install pillow-heif` (non inclus par défaut, lourd).
- **Estimation tokens** : `tiktoken` cible le tokenizer GPT-4 / Claude moderne ; précision ~95 % pour le français.
- **GUI macOS Apple Silicon** : nécessite Python ARM64 pour la version pip (les binaires standalone sont compilés natifs).

---

## Développement

### Setup local

```bash
git clone https://github.com/cg97411/trimtokens.git
cd trimtokens
python -m venv .venv
source .venv/bin/activate  # ou .venv\Scripts\activate sous Windows
pip install -e ".[ocr,gui,dev]"
```

### Tests + lint + types

```bash
pytest                     # 127 tests
ruff check src tests       # lint
ruff format src tests      # format
mypy src                   # type-check strict
```

### Build local (PyInstaller)

```bash
python build.py            # CLI + GUI pour l'OS courant
python build.py --cli-only # CLI seule
python build.py --clean    # nettoyage avant build
```

### Architecture

```
src/trimtokens/
├── __init__.py            # __version__
├── models.py              # ExtractOptions, Section, ExtractedDocument, CleanStats, ProcessResult
├── config.py              # Paths Win/Unix + TRIMTOKENS_HOME
├── stats.py               # estimate_tokens (tiktoken + fallback), compute_stats
├── core.py                # Dispatch extension → extracteur → cleaner → renderer
├── cli.py                 # typer + rich (CLI)
├── gui.py                 # customtkinter + tkinterdnd2 (GUI)
├── cleaners/
│   └── pipeline.py        # Pipeline 11 étapes
├── renderer/
│   └── markdown.py        # Front-matter YAML + sections
├── ocr/
│   ├── engine.py          # pytesseract wrapper
│   ├── preprocess.py      # Pillow + opencv preprocessing
│   ├── cache.py           # SHA-256 disk cache
│   └── parallel.py        # ProcessPoolExecutor + rich progress
└── extractors/
    ├── pdf.py             # pymupdf + OCR routing
    ├── docx.py            # python-docx
    ├── pptx.py            # python-pptx
    ├── xlsx_csv.py        # openpyxl + csv stdlib
    ├── html.py            # bs4 + markdownify
    ├── txt_md.py          # encoding-detected read
    ├── rtf.py             # striprtf
    ├── image.py           # OCR systématique
    └── _encoding.py       # BOM + chardet detection
```

---

## Contribuer

Les PR sont les bienvenues. Avant d'ouvrir une PR :

1. Forker + brancher (`git checkout -b feat/ma-feature`)
2. Lancer la suite complète : `pytest && ruff check src tests && mypy src`
3. Ajouter des tests pour toute nouvelle fonctionnalité
4. Mettre à jour `CHANGELOG.md` sous `[Unreleased]`
5. Ouvrir la PR avec une description claire du problème et de la solution

Pour les bugs : ouvrir une issue avec un cas reproductible minimum (un petit fichier sample joint).

---

## Licence

[MIT](LICENSE) © 2026 cg97411

---

## Remerciements

Construit sur les épaules de :
- [PyMuPDF](https://pymupdf.readthedocs.io/) — extraction PDF
- [Tesseract](https://github.com/tesseract-ocr/tesseract) + [pytesseract](https://github.com/madmaze/pytesseract) — OCR
- [python-docx](https://python-docx.readthedocs.io/) / [python-pptx](https://python-pptx.readthedocs.io/) / [openpyxl](https://openpyxl.readthedocs.io/) — formats Office
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) + [markdownify](https://github.com/matthewwithanm/python-markdownify) — HTML
- [typer](https://typer.tiangolo.com/) — CLI
- [customtkinter](https://github.com/TomSchimansky/CustomTkinter) + [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) — GUI
- [Rich](https://github.com/Textualize/rich) — affichage console
- [tiktoken](https://github.com/openai/tiktoken) — estimation tokens
