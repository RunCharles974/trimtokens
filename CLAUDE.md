# TrimTokens — Project Memory

> *Allégez vos documents pour l'IA, en local. — Lighten your docs locally, AI-ready.*

Outil Python local qui transforme PDF/DOCX/PPTX/XLSX/images/HTML en Markdown compact pour réduire tokens Claude/IA de 90+ %. Anciennement nommé TokensClean (dossier `C:\TrimTokens\` conservé pour compat).

Spec complète : [`TrimTokens.md`](./TrimTokens.md).

## Contraintes non-négociables
- 100 % local, zéro appel réseau, zéro fuite
- Portable Windows / macOS / Linux
- Python 3.10+, typé `from __future__ import annotations`, `mypy --strict` clean
- Lint `ruff`, format `ruff format`
- Tests `pytest`, couverture > 70 % pipeline + extracteurs
- Zéro `print()` dans code métier (logging + `rich.logging.RichHandler`)
- GUI réutilise exactement le pipeline CLI, zéro duplication

## Layout
- `src/trimtokens/` (src-layout best practice)
- Entry points : `trimtokens` (CLI typer) + `trimtokens-gui` (customtkinter)
- Un module par extracteur (`extractors/pdf.py`, `extractors/docx.py`, etc.)
- Signature unique : `extract(path: Path, options: ExtractOptions) -> ExtractedDocument`
- Modules dédiés : `cleaners/`, `ocr/` (engine + cache + preprocess + parallel), `renderer/`, `stats.py`, `config.py`, `core.py` (dispatch)

## Stack
- PDF + routing OCR : `pymupdf` (fitz)
- OCR : `pytesseract` + `Pillow` + `opencv-python-headless`
- DOCX `python-docx`, PPTX `python-pptx`, XLSX `openpyxl`
- HTML `beautifulsoup4` + `markdownify`, RTF `striprtf`
- CLI `typer`, GUI `customtkinter` + `tkinterdnd2`, clipboard `pyperclip`
- Tokens `tiktoken` (`cl100k_base`) + fallback `len/4`
- Encoding `chardet`, YAML `pyyaml`, TOML `tomllib` 3.11+ / `tomli` 3.10
- Console `rich`, cache `diskcache` ou maison
- Build `pyinstaller`, packaging `hatchling`

## Paths config / cache / logs
- Linux/macOS : `~/.trimtokens/{config.toml,cache/,logs/}`
- Windows : `%APPDATA%\trimtokens\`
- Override : env var `TRIMTOKENS_HOME`
- Cache OCR : SHA-256(fichier + paramètres) → résultat texte, jamais ré-OCR même doc

## Pipeline cleaning (11 étapes obligatoires, ordre exact)
1. Unicode NFKC
2. Suppression invisibles (U+200B, U+200C, U+200D, U+FEFF, U+00AD, contrôles non imprimables)
3. Ligatures typo (ﬁ→fi, ﬂ→fl, ﬀ→ff, ﬃ→ffi, ﬄ→ffl)
4. Recollage mots coupés fin de ligne (`exem-\nple` → `exemple`)
5. Espaces multiples / tabs → un espace
6. Sauts de ligne consécutifs ≤ 2
7. Headers/footers récurrents (ligne sur ≥ 30 % des pages OU `^Page \d+( / \d+)?$`)
8. Dédup paragraphes identiques (≥ 3 occurrences)
9. Suppression lignes ponctuation/séparateurs seuls
10. Trim + EOL → `\n`
11. Estimation tokens

## OCR — règles
- Tesseract via `pytesseract`, langs défaut `fra+eng`
- PSM adaptatif : 6 défaut, 1 multi-colonnes, 11 éparse ; OEM 3
- Préprocess : grayscale → OSD rotation → upscale si DPI<300 → Otsu/adaptatif → denoise → crop bordures
- Trigger OCR PDF page-par-page : < 50 chars natifs ET surface > seuil
- Parallel `ProcessPoolExecutor`, workers = `cpu_count - 1`, `rich.progress`
- Fallback gracieux si Tesseract absent : warning + skip OCR, garde texte natif

## Front-matter MD obligatoire
YAML : `source`, `type`, `extracted_at` ISO 8601, `ocr_used`, `ocr_pages[]`, `language`, `stats.{original_size_bytes,cleaned_size_bytes,reduction_percent,original_chars,cleaned_chars,tokens_estimated,tokens_reduction_percent}`.

## Structure MD par format
- PDF > 1 page : `## Page N`, OCR : `## Page N (OCR)`
- PPTX : `## Slide N — Titre` + `### Notes du présentateur`
- DOCX : préserver `Heading N` natifs
- XLSX/CSV : `## Feuille : Nom` + table MD
- Image : `## Texte extrait (OCR)`

## Plan dev (12j solo)
| Phase | Contenu | Modèle Claude |
|-------|---------|---------------|
| 0 | Setup repo, pyproject, CI skeleton | **Haiku 4.5** |
| 1 | models, cleaners pipeline, renderer, stats, config, tests | **Opus 4.7** |
| 2 | Extracteurs txt/md/html/docx/pptx/xlsx/rtf | **Sonnet 4.6** |
| 3 | PDF + OCR (preprocess, cache, parallel) | **Opus 4.7** |
| 4 | CLI typer + rich | **Sonnet 4.6** |
| 5 | GUI customtkinter + tkinterdnd2 | **Sonnet 4.6** |
| 6 | PyInstaller build.py + workflows release | **Opus 4.7** |
| 7 | README.fr, CHANGELOG, polish mypy/ruff | **Haiku 4.5** |

Phases 1 → 2 → 3 séquentielles bloquantes. 4 et 5 parallélisables. 6 et 7 fin.

## Risques connus
1. PyInstaller + tkinterdnd2 hidden imports = casse-tête, dry-run dès phase 5
2. Heuristique headers/footers à valider sur vrais PDF (fixture représentative)
3. Tesseract dep système → CI doit l'installer (apt/brew/choco/winget)
4. Cache OCR perf = risque principal phase 3, prototype tôt

## Livrables finaux (spec §"CE QUE TU DOIS PRODUIRE")
Arborescence complète, `pyproject.toml`, `README.md` fr, `requirements*.txt`, `LICENSE` MIT, `CHANGELOG.md` Keep a Changelog, `.gitignore`, package Python, ≥3 tests pytest (pipeline + PDF + DOCX), `build.py` PyInstaller, `.github/workflows/release.yml`, `config.example.toml`.

## Ordre génération recommandé spec §300
pyproject.toml → models.py → cleaners/ → ocr/ → extracteurs → renderer → core → CLI → GUI → tests → build → README.

## État actuel (2026-05-25)
Greenfield, seul `TrimTokens.md` (spec) + ce `CLAUDE.md` présents. Aucune ligne de code écrite. Repo git non initialisé.
