# MISSION

Crée un outil Python professionnel et autonome appelé **TrimTokens** qui transforme n'importe quel document (PDF, DOCX, PPTX, XLSX, images, HTML) en **Markdown propre, compact et prêt à coller dans Claude**, afin de réduire massivement la consommation de tokens.

Contraintes fortes :
- **100 % local**, aucun appel API, aucune fuite réseau.
- **Portable** : installable proprement sur Windows, macOS et Linux ; exportable en exécutable standalone pour transfert sur d'autres PC sans environnement Python.
- **Qualité professionnelle** : code typé, testé, packagé, documenté.

---

# CONTEXTE & PROBLÈME RÉSOLU

Les documents bruts envoyés à Claude contiennent :
- métadonnées XML inutiles (PPTX/DOCX/XLSX = ZIP de XML très verbeux),
- sauts de page, en-têtes/pieds répétés,
- espaces multiples, tabulations, caractères Unicode parasites (zero-width, BOM, soft hyphens…),
- doublons, boilerplate (mentions légales, footers répétés à chaque page),
- images encodées qui ne servent à rien pour le texte.

**Objectif chiffré : 60 à 90 % de réduction de tokens** sans perte d'information sémantique.

---

# SPÉCIFICATIONS FONCTIONNELLES

## 1. Formats d'entrée supportés
- **PDF** (texte natif + scannés avec OCR optimisé)
- **DOCX** (Word, préserver hiérarchie des titres + listes)
- **PPTX** (PowerPoint, slides + notes du présentateur)
- **XLSX / CSV** (tables Markdown par feuille)
- **Images** : PNG, JPG, JPEG, WEBP, TIFF, BMP, HEIC (OCR optimisé)
- **HTML / HTM** (conversion Markdown intelligente)
- **TXT / MD** (nettoyage des espaces et caractères parasites)
- **RTF** (via `striprtf`)
- **ODT / ODP** (optionnel, via `odfpy` si simple à intégrer)

## 2. OCR — pipeline optimisé

Moteur principal : **Tesseract** via `pytesseract`, avec optimisations.

**Détection intelligente du besoin OCR** :
- Pour un PDF : page par page, mesurer la quantité de texte extractible. Si une page contient < 50 caractères extractibles natifs alors qu'elle a une surface > X cm², déclencher l'OCR pour cette page uniquement (jamais sur tout le PDF si seules 2 pages sont scannées).
- Pour une image : OCR systématique.
- Cache OCR sur disque (hash SHA-256 du fichier + paramètres → résultat OCR) dans `~/.trimtokens/cache/ocr/` pour ne jamais ré-OCR le même document.

**Pré-traitement des images** (via Pillow + `opencv-python-headless`) :
1. Conversion en niveaux de gris
2. Auto-rotation si l'image est inclinée (détection via Tesseract OSD : `pytesseract.image_to_osd`)
3. Redimensionnement si DPI < 300 (upscale x2 ou x3 selon taille initiale)
4. Binarisation adaptative (Otsu ou seuillage adaptatif local)
5. Débruitage léger (median blur ou fastNlMeansDenoising)
6. Suppression des bordures noires de scan si détectées

**Configuration Tesseract** :
- Langues par défaut : `fra+eng` (configurables via `--ocr-lang`)
- Mode PSM (Page Segmentation Mode) adaptatif :
  - PSM 6 par défaut (bloc uniforme de texte)
  - PSM 1 si la page contient probablement plusieurs colonnes (détecté heuristiquement)
  - PSM 11 pour les images très éparses
- OEM 3 (LSTM par défaut)
- Whitelist/blacklist de caractères désactivée par défaut

**Parallélisation** : OCR des pages d'un PDF en parallèle via `concurrent.futures.ProcessPoolExecutor` (nombre de workers = `os.cpu_count() - 1`). Progress bar `rich.progress`.

**Fallback gracieux** : si Tesseract n'est pas trouvé sur le système, log un warning clair avec instructions d'installation par OS et continuer sans OCR (le texte natif extractible est conservé).

## 3. Interfaces utilisateur

### 3.1 CLI (interface principale)
- `trimtokens fichier.pdf` → écrit `fichier.clean.md` à côté
- `trimtokens ./dossier/ --recursive --out ./clean/`
- `trimtokens fichier.pdf --stdout`
- `trimtokens fichier.pdf --clipboard` (copie le Markdown nettoyé dans le presse-papiers)

Options CLI :
- `--format {md,txt,json}` (défaut `md`)
- `--ocr-lang fra+eng`
- `--no-ocr` / `--force-ocr` (forcer OCR même si texte natif présent)
- `--ocr-psm N` (override manuel du PSM)
- `--max-chars N`
- `--stats` (affiché par défaut, désactivable via `--quiet`)
- `--aggressive` (déduplication maximale, suppression footers/headers répétés)
- `--no-cache` (ignorer le cache OCR)
- `--workers N` (override du nombre de workers parallèles)
- `--quiet` / `--verbose`
- `--version`

### 3.2 Drag & drop — GUI minimaliste
Application graphique simple en **`customtkinter`** (look moderne, multi-plateforme) :
- Fenêtre principale : grande zone de dépôt "Glissez vos fichiers ici" (utiliser `tkinterdnd2` pour le drag & drop natif depuis l'explorateur)
- Support multi-fichiers : déposer 1 ou N fichiers, ou un dossier entier
- Sous la zone de dépôt :
  - Sélecteur de langue OCR (multi-select : Français, Anglais, Allemand, Espagnol, Italien…)
  - Toggle "Mode agressif"
  - Toggle "Copier dans le presse-papiers après nettoyage"
  - Toggle "Ouvrir le fichier nettoyé après traitement"
- Pendant le traitement : barre de progression + log déroulant
- À la fin : tableau récapitulatif (fichier, taille avant/après, tokens avant/après, statut)
- Bouton "Ouvrir le dossier de sortie"

L'app GUI doit être lançable via :
- `trimtokens-gui` (entry point séparé)
- Double-clic sur un raccourci sur le bureau

**Important** : la GUI réutilise exactement le même pipeline que la CLI (aucune duplication de logique).

## 4. Pipeline de nettoyage (commun à tous les extracteurs)

1. Normalisation Unicode (NFKC)
2. Suppression des caractères invisibles : zero-width (U+200B, U+200C, U+200D, U+FEFF), soft hyphen (U+00AD), caractères de contrôle non imprimables
3. Conversion des ligatures typographiques (ﬁ → fi, ﬂ → fl, ﬀ → ff, ﬃ → ffi, ﬄ → ffl)
4. Recollage des mots coupés en fin de ligne (`exem-\nple` → `exemple`)
5. Suppression des espaces multiples, tabulations → un seul espace
6. Limitation des sauts de ligne consécutifs à 2 maximum
7. Détection et suppression des en-têtes / pieds de page récurrents (heuristique : ligne identique apparaissant sur ≥ 30 % des pages d'un PDF, ou numérotation de page de type `^Page \d+( / \d+)?$`)
8. Déduplication des paragraphes strictement identiques répétés (≥ 3 occurrences)
9. Suppression des lignes ne contenant que de la ponctuation ou des séparateurs (`---`, `___`, `***` répétés)
10. Trim final + normalisation des fins de ligne en `\n`
11. Estimation des tokens : `tiktoken` avec `cl100k_base` si dispo, sinon fallback `len(text) / 4`

## 5. Format de sortie Markdown (`*.clean.md`)

```markdown
---
source: nom_original.pdf
type: pdf
extracted_at: 2026-05-25T14:32:00Z
ocr_used: true
ocr_pages: [3, 7, 12]
language: fra+eng
stats:
  original_size_bytes: 2516582
  cleaned_size_bytes: 18432
  reduction_percent: 99.3
  original_chars: 312450
  cleaned_chars: 41220
  tokens_estimated: 10300
  tokens_reduction_percent: 87
---

# Titre du document (si extrait des métadonnées)

## Page 1

Contenu textuel propre…

## Page 2

…
```

Règles de structuration :
- **PDF** : un `##` par page (`## Page N`) si > 1 page ; marquer les pages OCR avec `## Page N (OCR)`
- **PPTX** : un `##` par slide (`## Slide N — Titre`) ; bloc `### Notes du présentateur` séparé
- **DOCX** : préserver les niveaux de titres natifs (`Heading 1` → `#`, `Heading 2` → `##`, etc.) ; listes à puces et numérotées préservées
- **XLSX/CSV** : un `##` par feuille (`## Feuille : Nom`), puis table Markdown standard
- **HTML** : conversion via `markdownify` (titres, listes, liens préservés, scripts/styles supprimés)
- **Images / OCR** : `## Texte extrait (OCR)` puis contenu brut

Front-matter YAML obligatoire avec stats complètes.

## 6. Portabilité & déploiement multi-PC

Trois modes d'installation supportés :

### Mode 1 — Installation classique (développeurs)
```bash
pip install trimtokens
```
Publié sur PyPI (ou installable localement via `pip install .`).

### Mode 2 — Installation isolée avec `pipx` (utilisateurs avancés)
```bash
pipx install trimtokens
```

### Mode 3 — Exécutable standalone (utilisateurs sans Python) ⭐ priorité haute
Générer des **binaires autonomes** avec **PyInstaller** ou **Nuitka** pour les 3 OS :
- `trimtokens-windows-x64.exe` (CLI) + `trimtokens-gui-windows-x64.exe` (GUI)
- `trimtokens-macos-arm64` et `trimtokens-macos-x64`
- `trimtokens-linux-x64` (AppImage si possible)

Ces binaires embarquent Python et toutes les dépendances Python.
⚠️ Tesseract reste une dépendance système externe (trop lourd à embarquer) → l'installeur Windows doit pouvoir détecter Tesseract et proposer un lien d'installation si absent.

Fournir :
- Un script `build.py` (ou `build.sh` + `build.ps1`) qui produit les exécutables
- Un workflow GitHub Actions `.github/workflows/release.yml` qui build et publie les binaires sur les Releases GitHub à chaque tag `v*`
- Documentation claire pour installer Tesseract sur chaque OS (chocolatey/winget pour Windows, brew pour macOS, apt/dnf pour Linux)

### Configuration utilisateur portable
- Fichier de config optionnel : `~/.trimtokens/config.toml` (langues OCR par défaut, mode agressif par défaut, etc.)
- Cache : `~/.trimtokens/cache/`
- Logs : `~/.trimtokens/logs/`
- Sur Windows : utiliser `%APPDATA%\trimtokens\`
- Possibilité de surcharger via variable d'environnement `TRIMTOKENS_HOME`

## 7. Architecture du projet

Laisse au développeur la liberté de l'arborescence finale, mais respecter ces principes :
- Layout `src/trimtokens/` (best practice moderne)
- Package importable `trimtokens`
- Deux entry points :
  - `trimtokens = "trimtokens.cli:app"`
  - `trimtokens-gui = "trimtokens.gui:main"`
- Un module par extracteur (un fichier par format) pour faciliter l'extension
- Module dédié au pipeline de nettoyage (réutilisable)
- Module dédié à l'OCR avec son cache
- Module dédié au renderer Markdown
- Module dédié aux stats et estimation tokens
- Tests `pytest` avec fixtures réalistes (PDF natif, PDF scanné de test, DOCX, PPTX, image avec texte)

Signature unique pour chaque extracteur :
```python
def extract(path: Path, options: ExtractOptions) -> ExtractedDocument: ...
```
avec `ExtractedDocument` un dataclass contenant : titre, sections (liste de `Section(header, content, metadata)`), métadonnées globales, type de source, drapeau `ocr_used`, liste `ocr_pages`.

Le core dispatch par extension → extracteur → pipeline de nettoyage → renderer Markdown.

## 8. Librairies recommandées
- **PDF + OCR routing** : `pymupdf` (alias `fitz`)
- **OCR** : `pytesseract` + `Pillow` + `opencv-python-headless`
- **DOCX** : `python-docx`
- **PPTX** : `python-pptx`
- **XLSX** : `openpyxl`
- **HTML** : `beautifulsoup4` + `markdownify`
- **RTF** : `striprtf`
- **CLI** : `typer`
- **GUI** : `customtkinter` + `tkinterdnd2`
- **Clipboard** : `pyperclip`
- **Tokens** : `tiktoken`
- **Encoding** : `chardet`
- **Front-matter YAML** : `pyyaml`
- **UI console** : `rich`
- **Config** : `tomli` (3.10) / `tomllib` (3.11+)
- **Cache** : `diskcache` ou implémentation maison simple
- **Packaging** : `pyinstaller` (build) ; `pyproject.toml` avec `hatchling` ou `setuptools` (distribution)
- **Tests** : `pytest`, `pytest-cov`

## 9. Récapitulatif console (via `rich`)

```
✓ fichier.pdf → fichier.clean.md
┌─────────────────┬──────────┬──────────┬─────────┐
│ Métrique        │ Avant    │ Après    │ Gain    │
├─────────────────┼──────────┼──────────┼─────────┤
│ Taille          │ 2.4 MB   │ 18 KB    │ -99 %   │
│ Caractères      │ 312 450  │ 41 220   │ -87 %   │
│ Tokens estimés  │ ~78 000  │ ~10 300  │ -87 %   │
│ OCR             │ 3 pages  │ —        │ —       │
│ Durée           │ —        │ 4.2s     │ —       │
└─────────────────┴──────────┴──────────┴─────────┘
```

## 10. Qualité & contraintes techniques

- **Python 3.10+**
- Code typé partout (`from __future__ import annotations`, type hints complets, validé via `mypy --strict`)
- Linting via `ruff` (config dans `pyproject.toml`)
- Formatage via `ruff format` ou `black`
- Gestion d'erreurs robuste : jamais de crash global sur un document partiellement corrompu ; chaque page/slide/feuille est traitée en isolation
- Logging structuré (module `logging` + `rich.logging.RichHandler`)
- Aucun `print()` direct dans le code métier
- Couverture de tests > 70 % sur le pipeline de nettoyage et les extracteurs
- Tests d'intégration sur des fixtures réelles (au moins 1 PDF natif, 1 PDF scanné, 1 DOCX, 1 PPTX, 1 image)
- README en français avec :
  - Présentation et objectifs
  - Captures d'écran de la GUI
  - Installation détaillée pour chaque OS (3 modes)
  - Installation de Tesseract pour chaque OS
  - Exemples CLI complets
  - Tableau comparatif des gains tokens par type de document
  - Section "Limitations connues"
  - Section "Contribuer"
- `CHANGELOG.md` au format Keep a Changelog
- `LICENSE` (MIT recommandé)
- `.gitignore` Python standard
- `pyproject.toml` complet avec métadonnées projet, dépendances optionnelles (`[ocr]`, `[gui]`, `[dev]`)
- Workflow GitHub Actions pour : tests sur les 3 OS, lint, build des binaires sur tag

---

# CE QUE TU DOIS PRODUIRE

1. Arborescence complète du projet
2. `pyproject.toml` (avec entry points, dépendances optionnelles, métadonnées)
3. `README.md` complet en français
4. `requirements.txt` minimal + `requirements-dev.txt`
5. `LICENSE` (MIT)
6. `CHANGELOG.md` initial
7. `.gitignore`
8. Tous les fichiers Python du package, organisés en modules cohérents
9. Au moins 3 tests pytest (pipeline de nettoyage, extracteur PDF, extracteur DOCX) avec fixtures
10. Le script `build.py` PyInstaller multi-OS
11. Le workflow `.github/workflows/release.yml`
12. Un `config.example.toml` documenté

Commence par présenter l'arborescence complète, puis génère les fichiers dans cet ordre :
1. `pyproject.toml`
2. Modèles de données (`models.py`)
3. Pipeline de nettoyage (`cleaners/`)
4. Module OCR (`ocr/`)
5. Extracteurs (un par un)
6. Renderer Markdown
7. Core / orchestrateur
8. CLI
9. GUI
10. Tests
11. Script de build
12. README + docs annexes