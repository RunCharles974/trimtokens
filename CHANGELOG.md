# Changelog

Tous les changements notables de ce projet sont documentés dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet suit le [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

### Changed
- Refactor GUI MVVM léger (cf audit §GUI "Refactor MVVM ou MVC léger") :
  `gui.py` (648 lignes) → package `gui/` à 4 modules :
  - `utils.py` : helpers purs (`_parse_dropped_paths`, `_format_bytes`,
    `_format_count`, `_open_in_explorer`, `SUPPORTED_LANGUAGES`)
  - `state.py` : `AppState` dataclass (processing, output_dir, results,
    log_line_targets, current_viewer_path) + `FileResult` dataclass (remplace
    `dict[str, Any]` non typé, compat lecture `__getitem__`)
  - `services.py` : `ProcessingService` (thread + callbacks marshallés via
    `dispatch`) avec `ProcessingCallbacks` (4 hooks) + `cancel()` opt-in
  - `app.py` : `TrimTokensGUI` View slim (binds widgets, délègue à
    state/services). Surface API publique 100% préservée (tests existants
    passent sans modification).
  11 nouveaux tests headless (`test_gui_state.py`) — couvrent state/service
  sans Tk.

### Added
- CLI `--profile` : table Rich breakdown StepMetrics par étape de nettoyage
  (chars in/out, Δ chars, Δ %, ms, % total). Ferme la boucle observabilité
  pipeline ouverte par `cleaners/steps.py`. 9 nouveaux tests.
- `clean()` : argument `metrics_sink: list[StepMetrics] | None` optionnel.
  Si fourni, `Pipeline.run()` métriques sont étendues dans la liste (caller
  opt-in, coût zéro quand `None`).
- `ProcessResult.pipeline_metrics` : liste agrégée de `StepMetrics` (somme
  chars/ms par nom d'étape) collectée par `core.process` (toutes sections).
  Loggé via event `cleaning_pipeline_complete`.
- `cleaners/steps.py::aggregate_metrics(metrics)` : agrégateur somme par nom
  préservant l'ordre de première apparition.
- Multiprocessing OCR PDF effectif (cf audit §Performance "Multiprocessing OCR").
  `extractors/pdf.py` câble désormais `ocr.parallel.parallel_map` pour les pages
  non cachées quand `options.workers != 1`. Nouveau `_ocr_worker` top-level
  (picklable) résout le backend dans chaque process enfant via le registry.
  `_resolve_ocr_workers(requested, num_items)` : `workers=0` → `default_workers()`
  borné par `num_items` ; `num_items<=1` → séquentiel (évite spawn overhead) ;
  `workers>=1` → exact borné. `OCR_COMPLETE` log inclut `workers=` effectif.
  13 nouveaux tests.
- `logging_setup.py` : logging structuré (cf audit §Robustesse "Logging structuré").
  Classes `JSONFormatter` (JSON Lines : ts/level/logger/event/data/module/exc) et
  `ConsoleStructuredFormatter` (suffix `k=v`). Helper `log_event(logger, event, **fields)`.
  Catalogue `Events` (snake_case stable) : `extraction_start/complete/failed`,
  `ocr_start/complete/skipped`, `ocr_cache_hit/miss`, `cleaning_pipeline_complete`.
  `setup_logging(level, console, json_file, err_console)` configure les deux canaux.
  11 nouveaux tests.
- CLI : flag `--log-file PATH` (JSON Lines append). Override via `[logging] json_file`
  dans la config TOML.
- Points d'observabilité ajoutés : `core.process` (start/complete/failed avec
  durée_ms, sections, ocr_used, reduction_percent), `pdf._ocr_pages`
  (start/complete/skipped avec backend, pages, cache_hits, duration_ms),
  `image.extract` (start/complete/skipped/cache_hit).
- `LoggingConfig.json_file` (TOML `[logging] json_file = "..."`).
- `ocr/backend.py` : Protocol `OCREngine` (`name`, `is_available`, `extract`,
  `install_hint`). Registry `register_backend` / `get_backend` / `list_backends` /
  `unregister_backend`. `TesseractBackend` enregistré par défaut. Permet
  d'enficher EasyOCR, PaddleOCR, OCR GPU, OCR cloud sans modifier les call sites
  (cf audit §OCR "Pas de backend abstrait"). 13 nouveaux tests.
- `ExtractOptions.ocr_backend` : sélection du backend par nom (défaut `"tesseract"`).
- `extractors/pdf.py` + `extractors/image.py` : route désormais vers le backend
  via `get_backend(options.ocr_backend)`. Clé cache OCR préfixée par le nom du
  backend pour éviter de mélanger les résultats entre moteurs.
- `config.py` enrichi : dataclasses `TrimTokensConfig`, `OCRConfig`, `PDFConfig`,
  `CleaningConfig`, `OutputConfig`, `CacheConfig`, `LoggingConfig`. Loader
  `load_config(path)` lit TOML (tomllib 3.11+, tomli fallback 3.10),
  `to_extract_options()` projette vers `ExtractOptions`. Clés inconnues ignorées
  (forward-compat), TOML malformé → `ConfigError`. 9 nouveaux tests.
- CLI : flag `--config PATH`. Charge un TOML qui devient la couche par défaut,
  les flags CLI explicites surchargent les champs (détection via
  `ctx.get_parameter_source`). Comportement historique préservé sans `--config`.
- `config.example.toml` : nouvelle section `[pdf]` documentant seuils
  `min_native_chars_per_page`, `ocr_dpi`, `image_based_*`. Section `[cleaning]`
  enrichie (drop_empty_pages, merge_continuations, smart_filter, filter_*).
- `cleaners/steps.py` : pipeline orienté étapes (plugin pattern). Classes `Pipeline`,
  `CleaningStep` (Protocol), `StepMetrics`, factory `default_pipeline(aggressive=)`.
  Permet activation/désactivation par étape (`pipeline.without(...)`), injection custom
  (`pipeline.insert_after(...)`), profiling par étape (chars in/out + ms). 12 nouveaux tests.
- `clean()` accepte un argument `pipeline: Pipeline | None` pour injection custom ;
  délègue désormais l'orchestration interne à `Pipeline.run()` (zéro régression).
- `exceptions.py` : hiérarchie d'erreurs métier (`TrimTokensError`, `UnsupportedFormatError`,
  `MissingDependencyError`, `ExtractionError`, `OCRExtractionError`, `ConfigError`)
- `ExtractOptions` : seuils PDF/OCR externalisés (`pdf_min_native_chars_per_page`,
  `pdf_ocr_dpi`, `pdf_image_based_max_chars_per_page`, `pdf_image_based_min_images_per_page`,
  `pdf_image_based_min_pages`) — permettent tuning sans modifier le code
- `pyproject.toml` : `[tool.pytest.ini_options] pythonpath = ["src"]` (suppr besoin
  `PYTHONPATH=src` ou `pip install -e .` pour exécuter les tests)

### Changed
- `core._resolve_extractor` lève désormais `UnsupportedFormatError` (sous-classe de
  `ValueError` pour préserver la compat des appelants existants)
- `extractors/pdf.py` : `detect_image_based()` accepte les seuils en kwargs (alimentés
  par `ExtractOptions`) au lieu de constantes module figées
- `extractors/rtf.py` : import `striprtf` protégé, `MissingDependencyError` levée à
  l'extraction si le package est absent (au lieu d'échouer à l'import de `trimtokens`)

## [0.1.0] — 2026-05-26

### Added

#### Phase 0 — Setup
- Squelette initial du projet
- `pyproject.toml` avec entry points CLI et GUI, dépendances optionnelles `[ocr]`/`[gui]`/`[dev]`
- Configuration `ruff` (lint + format) et `mypy --strict`
- Configuration `pytest` avec couverture
- Layout `src/trimtokens/` (src-layout)
- Workflow GitHub Actions CI (lint + tests sur Windows/macOS/Linux)
- `LICENSE` MIT, `.gitignore` Python, `CHANGELOG.md` Keep a Changelog
- Spec projet (`TrimTokens.md`) et mémoire projet (`CLAUDE.md`)
- **Phase 1 — Noyau** :
  - `models.py` : dataclasses `ExtractOptions`, `Section`, `ExtractedDocument`, `CleanStats`
  - `cleaners/pipeline.py` : pipeline 11 étapes (NFKC, invisibles, ligatures, recollage hyphen,
    espaces multiples, sauts de ligne ≤2, en-têtes/pieds récurrents PDF, dédup paragraphes ≥3,
    suppression lignes ponctuation/séparateurs, trim+EOL)
  - `stats.py` : estimation tokens via `tiktoken` (`cl100k_base`) avec fallback `len/4`,
    fonction `compute_stats` pour construction `CleanStats`
  - `renderer/markdown.py` : front-matter YAML obligatoire + rendu sections `##`
  - Tests Phase 1 : `test_pipeline.py` (24 cas couvrant les 11 étapes + pipeline complet),
    `test_renderer.py` (7 cas front-matter + sections), `test_stats.py` (7 cas tokens + stats)
- **Phase 2 — Extracteurs texte natif** :
  - `extractors/_encoding.py` : détection encodage (BOM UTF-8/16, UTF-8 strict, chardet, latin-1)
  - `extractors/txt_md.py` : TXT et MD via lecture binaire + détection encodage
  - `extractors/html.py` : HTML via BeautifulSoup (strip script/style/noscript/iframe/template/head)
    puis markdownify (ATX headings)
  - `extractors/docx.py` : DOCX via python-docx (préserve Heading N → `#`*N, listes à puces/numérotées, tables Markdown)
  - `extractors/pptx.py` : PPTX via python-pptx (`Slide N — Titre` par slide + `### Notes du présentateur`)
  - `extractors/xlsx_csv.py` : XLSX via openpyxl et CSV via stdlib (table MD par feuille, skip feuilles vides)
  - `extractors/rtf.py` : RTF via striprtf
  - `core.py` : dispatch extension → extracteur → cleaner (par section) → renderer ; retourne `ProcessResult`
  - `models.py` : ajout `ProcessResult` (document + stats + markdown)
  - `extractors/__init__.py` : `EXTENSION_MAP` complète (18 extensions)
  - Tests Phase 2 : `test_extractors.py` (18 cas — fixtures générées en mémoire via python-docx/pptx/openpyxl + core dispatch + erreurs format inconnu / fichier absent)
- **Phase 3 — PDF + OCR** :
  - `ocr/cache.py` : SHA-256(file_bytes + langs + psm), `OCRCache` disque, helpers `compute_cache_key` / `compute_file_cache_key`
  - `ocr/engine.py` : `is_tesseract_available()` (lru_cache), `detect_orientation()` via OSD,
    `ocr_pil_image()`, `ocr_file()`, `get_tesseract_install_hint()` (instructions OS)
  - `ocr/preprocess.py` : pipeline 6 étapes (grayscale, OSD rotation, upscale DPI<300 x2 ou x3,
    Otsu opencv ou fallback Pillow, median blur opencv, crop bordures conservatif ≥10 px)
  - `ocr/parallel.py` : `parallel_map()` via `ProcessPoolExecutor`, workers défaut `cpu_count-1`,
    progress bar `rich` avec spinner + bar + elapsed time, mode séquentiel si 1 item ou 1 worker
  - `extractors/pdf.py` : pymupdf page-par-page, détection texte natif < 50 chars → flag OCR,
    rasterisation 300 DPI, cache lookup, `strip_recurring_headers_footers` cross-pages,
    `Page N` / `Page N (OCR)` par section, fallback gracieux Tesseract absent
  - `extractors/image.py` : OCR systématique, cache sur bytes binaires,
    support HEIC opt-in via `pillow-heif` si installé
  - Tests Phase 3 : `test_ocr.py` (23 cas — cache déterministe/unicode/dir creation,
    engine availability, preprocess grayscale/upscale/binarize, PDF natif/multi-page,
    fallback sans Tesseract, image extractor)
- **Phase 4 — CLI typer** :
  - `cli.py` : commande `@app.command(name="trimtokens")` avec ctx + path Optional
    pour afficher l'aide sans argument
  - Flags : `--format {md,txt,json}`, `--out`, `--stdout`, `--clipboard`, `--recursive`,
    `--ocr-lang`, `--no-ocr`/`--force-ocr` (mutex), `--ocr-psm 0-13`, `--max-chars`,
    `--aggressive`, `--no-cache`, `--workers`, `--quiet`/`--verbose` (mutex), `--version`
  - Table récap Rich avec colonnes Métrique/Avant/Après/Gain (taille, caractères, tokens,
    OCR pages, durée)
  - Logging via `RichHandler` sur stderr, zéro `print()` dans le code métier
  - Helpers : `_format_bytes`, `_format_number` (espaces séparateurs), `_render_output`
    (md/txt/json), `_collect_input_files` (single Path → file ou dir avec recursion)
  - Clipboard `pyperclip` (fallback gracieux si indisponible)
  - Tests Phase 4 : `test_cli.py` (22 cas : version/help/no-args/formats/out/stdout/clipboard/
    recursive/non-recursive/quiet/verbose/aggressive/max-chars/workers/psm validation/mutex/
    invalid format/missing path/unsupported extension)
- **Phase 5 — GUI customtkinter + tkinterdnd2** :
  - `gui.py` : `TrimTokensGUI` class avec drop zone native (`tkinterdnd2.TkinterDnD.DnDWrapper`
    mixin sur `customtkinter.CTk`), thème blue + appearance System (light/dark auto OS)
  - Drop zone clickable (ouvre filedialog) avec parser `_parse_dropped_paths` (format Windows
    avec accolades pour paths à espaces)
  - Options : multi-select langues (FR/EN/DE/ES/IT, FR+EN par défaut), toggles agressif/forcer
    OCR/clipboard/open-after
  - Worker thread `threading.Thread` pour ne pas bloquer UI, dispatch via `root.after(0, ...)`
  - Progress bar + status label + journal défilant + récap final (total bytes avant/après)
  - Bouton "Ouvrir dossier de sortie" actif après traitement (utilise `os.startfile` Windows,
    `open` macOS, `xdg-open` Linux via `_open_in_explorer`)
  - Réutilise `core.process()` + `ExtractOptions` — aucune duplication de logique métier
  - Fallback ImportError : message d'installation `pip install trimtokens[gui]`
  - Tests Phase 5 : `test_gui.py` (8 cas — parser paths simples/accolades/vides/dégradés,
    langues supportées, imports module, instanciation Tk smoke test)
- **Phase 6 — Packaging & distribution** :
  - `build.py` : script PyInstaller pour CLI + GUI, détection OS/arch automatique
    (windows/macos/linux × x64/arm64), `--cli-only`/`--gui-only`/`--clean`/`--debug`
  - Hidden imports complets : `fitz`, `PIL._tkinter_finder`, extracteurs dispatchés
    dynamiquement (`trimtokens.extractors.pdf|docx|...`), `tiktoken_ext.openai_public`,
    `striprtf.striprtf`, `tkinterdnd2`, `customtkinter`, `darkdetect`
  - `collect_data_args()` embarque ressources tcl/tkdnd de tkinterdnd2 + thèmes JSON
    customtkinter (séparateur `;` Windows vs `:` Unix)
  - `--collect-all customtkinter` pour ramasser tous les sous-modules
  - `.github/workflows/release.yml` : trigger sur tag `v*`, matrix 4 builds
    (ubuntu/windows/macos-13 x64/macos-14 arm64), install Tesseract via apt/brew/choco,
    pytest avant build, smoke test `--version` sur exe produit, upload artifacts,
    publication `softprops/action-gh-release@v2` avec body markdown détaillé,
    détection prerelease (`-rc`/`-beta`/`-alpha`)
  - Tests Phase 6 : `test_build.py` (9 cas — existence, importable, detect_platform
    cohérent OS courant, hidden imports listés, collect_data_args structure,
    base_pyinstaller_cmd flags essentiels, conflit `--cli-only`/`--gui-only` rejeté)

#### Phase 7 — Polish & docs
- `README.md` complet en français (objectifs, gains, installation 3 modes × 3 OS,
  install Tesseract par OS, exemples CLI complets, format de sortie, pipeline 11 étapes,
  OCR détails, limitations connues, dev setup, architecture, contribuer, remerciements)
- Ruff lint clean : `B008` ignoré pour `src/trimtokens/cli.py` (typer.Option idiomatique),
  `RUF001/RUF002/RUF003` ignorés globalement (caractères unicode légitimes en français)
- Ruff format appliqué sur l'ensemble du code
- Mypy strict configuré dans `pyproject.toml` avec overrides pour deps sans stubs
  (fitz, pytesseract, cv2, tkinterdnd2, customtkinter, markdownify, striprtf, pillow_heif, diskcache)
- **127 tests pytest verts** : pipeline (28), extracteurs (18), ocr (23), cli (22),
  gui (8), build (9), renderer (7), stats (7), smoke (5)
- **Détection auto PDF image-based** + avertissement Tesseract :
  - `extractors/pdf.py::detect_image_based()` : analyse cleaned_pages (APRÈS strip
    headers récurrents) + total images. Critères : ≥ 3 pages, < 100 chars natifs/page,
    ≥ 2 images/page en moyenne
  - `_emit_image_based_warning()` : log warning multi-ligne avec métriques + raison
    (no_ocr OU Tesseract absent OU OCR vide) + hint d'installation par OS
  - `image_based: True` + `image_based_metrics` ajoutés au metadata
  - Front-matter YAML expose `image_based` + `image_based_metrics` quand détecté
  - CLI : bandeau jaune sous la table de stats si image-based et OCR pas appliqué
  - GUI : warning dans le journal avec instructions d'installation
  - Tests Phase Bonus : 4 cas (positif image-based, négatif texte abondant, négatif < 3 pages,
    doc vide → metrics page_count=0)
- **Filtrage intelligent (`--smart-filter`)** : détection auto pages non pertinentes
  - `cleaners/heuristics.py` : 3 détecteurs purs + orchestrateur
    - `detect_toc()` : titre `Sommaire/Table des matières/Contents` OU ≥ 5 lignes
      au format `texte ... numéro` (regex tolérante : 3+ points OU 4+ espaces OU tab)
    - `detect_bibliography()` : titre `Bibliographie/Références/References` OU
      ≥ 8 patterns de références sur la page (`[N]`, `(Auteur, année)`, ligne `N. Auteur`)
    - `detect_sparse()` : page avec < 30 mots
  - `analyze_pages()` → liste `PageAnalysis` (`is_toc`/`is_bibliography`/`is_sparse` + reasons)
  - `filter_pages()` → `(pages_kept, filtered_dict_par_categorie_1_indexed)`
  - `ExtractOptions` : `smart_filter` + sous-flags `filter_toc`/`filter_bibliography`/`filter_sparse`
  - `pdf.py` intègre après strip headers/footers, préserve mapping `original_idx`
    pour les headers `## Page N` corrects malgré filtrage
  - Front-matter YAML enrichi : section `filtered_pages: {toc: [...], bibliography: [...], sparse: [...]}`
  - CLI : `--smart-filter` / `-s`, `--keep-toc`, `--keep-bibliography`, `--keep-sparse`
  - GUI : checkbox "🧠 Filtre intelligent (TOC/biblio/éparses)"
  - Tests Phase Bonus : `test_heuristics.py` (17 cas — chaque détecteur isolé positif/négatif,
    titres FR + EN, analyze_pages mixte, filter_pages mapping, intégration PDF avec smart_filter
    activé et flags individuels)
- **Affichage absolu des tokens dans la GUI** :
  - Helpers `_format_bytes()` (Ko/Mo/Go) et `_format_count()` (espace fine séparateur)
  - Journal : message multi-ligne `Taille X → Y (-Z %)`, `Tokens ~X → ~Y (-Z %)`, `Durée Ns`
  - Recap footer : compteurs absolus bytes ET tokens, plus seulement %
  - Entries dict élargies avec `tokens_before` / `tokens_after`
- **Visionneuse Markdown intégrée à la GUI** :
  - Layout split horizontal : panneau de contrôle à gauche, visionneuse à droite
  - Window 1280×720 par défaut, minsize 1100×650
  - `CTkTextbox` readonly avec fonte monospace (Consolas 11) + wrap word
  - Auto-affichage du dernier fichier `.clean.md` après traitement
  - Double-clic sur une ligne du journal → affiche le fichier correspondant
  - Mapping `_log_line_targets` capturé au moment de chaque insert
  - Boutons d'action visionneuse : `📋 Copier` (vers presse-papiers), `📝 Ouvrir dans éditeur`
    (via `_open_in_explorer` natif OS), `🔄 Recharger` (re-lecture depuis disque)
  - Boutons désactivés tant qu'aucun fichier n'est chargé
  - Gestion d'erreur OSError : affiche `[Erreur lecture] ...` dans la visionneuse
  - Tests Phase Bonus : 3 cas supplémentaires (load file content, missing file graceful,
    log+target mapping)
- **`LanceTrim.bat`** : lanceur Windows pour TrimTokens
  - Sans argument → lance la GUI (`trimtokens.gui`)
  - `cli <args>` → lance la CLI avec arguments transférés
  - `--help` / `-h` → affiche l'aide du lanceur
  - Détecte automatiquement `.venv/` ou `venv/`, sinon Python global
  - Fallback `PYTHONPATH=src` si package non installé (mode développement)
  - Messages d'erreur français avec instructions d'installation
  - Pause sur erreur pour conserver la fenêtre ouverte
- **Localisation bilingue** :
  - `LICENSE` : texte MIT anglais original (valeur légale) + traduction française
    informative en seconde partie
  - `.github/workflows/ci.yml` : étapes nommées EN (FR), commentaires français
  - `.github/workflows/release.yml` : idem CI, body markdown release entièrement français
  - Classifiers PyPI dans `pyproject.toml` restent anglais (standards trove obligatoires)
  - Help typer hardcodé en anglais via click upstream (acceptable)

[Unreleased]: https://github.com/cg97411/trimtokens/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/cg97411/trimtokens/releases/tag/v0.1.0
