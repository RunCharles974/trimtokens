"""View principale TrimTokens (customtkinter + tkinterdnd2).

MVVM léger : la View `TrimTokensGUI` orchestre widgets + binds events ; les
trois concerns lourds sont externalisés (cf audit §GUI "Refactor MVVM léger") :

- État applicatif → `gui.state.AppState`
- Traitement asynchrone → `gui.services.ProcessingService`
- Helpers purs (parsing, formatage, OS) → `gui.utils`

Compat surface API : les attributs `root`, `drop_frame`, `progress`, `lang_vars`,
`viewer_text`, `viewer_file_label`, `viewer_copy_btn`, `viewer_open_btn`,
`viewer_refresh_btn` ainsi que `_show_in_viewer`, `_log`, `_log_line_targets`,
`_current_viewer_path` sont préservés (tests d'intégration).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from trimtokens.gui.services import ProcessingCallbacks, ProcessingService
from trimtokens.gui.state import AppState, FileResult
from trimtokens.gui.utils import (
    SUPPORTED_LANGUAGES,
    _format_bytes,
    _format_count,
    _open_in_explorer,
    _parse_dropped_paths,
)
from trimtokens.models import ExtractOptions, ProcessResult

log = logging.getLogger(__name__)


class TrimTokensGUI:
    """Fenêtre principale TrimTokens."""

    def __init__(self) -> None:
        import customtkinter as ctk
        from tkinterdnd2 import DND_FILES, TkinterDnD

        self._ctk = ctk
        self._DND_FILES = DND_FILES

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):  # type: ignore[misc, valid-type]
            def __init__(self) -> None:
                super().__init__()
                self.TkdndVersion = TkinterDnD._require(self)

        self.root = DnDCTk()
        self.root.title("TrimTokens")
        self.root.geometry("1280x720")
        self.root.minsize(1100, 650)

        # État applicatif extrait dans `gui.state.AppState`.
        self.state = AppState()
        # Service de traitement asynchrone (thread + dispatch Tk).
        self.service = ProcessingService(dispatch=self._dispatch)

        self._build_ui()
        self._setup_drop_target()

    # ------------------------------------------------------------------
    # Compat layer : exposer state comme attributs directs sur l'instance
    # pour préserver l'API publique consommée par les tests historiques.
    # ------------------------------------------------------------------

    @property
    def results(self) -> list[FileResult]:
        return self.state.results

    @results.setter
    def results(self, value: list[FileResult]) -> None:
        self.state.results = value

    @property
    def output_dir(self) -> Path | None:
        return self.state.output_dir

    @output_dir.setter
    def output_dir(self, value: Path | None) -> None:
        self.state.output_dir = value

    @property
    def _processing(self) -> bool:
        return self.state.processing

    @_processing.setter
    def _processing(self, value: bool) -> None:
        self.state.processing = value

    @property
    def _log_line_targets(self) -> dict[int, Path]:
        return self.state.log_line_targets

    @property
    def _current_viewer_path(self) -> Path | None:
        return self.state.current_viewer_path

    @_current_viewer_path.setter
    def _current_viewer_path(self, value: Path | None) -> None:
        self.state.current_viewer_path = value

    # ------------------------------------------------------------------
    # Construction UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        ctk = self._ctk

        self.root.grid_columnconfigure(0, weight=0, minsize=560)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self.root, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)

        right = ctk.CTkFrame(self.root, fg_color=("gray92", "gray18"), corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)

        self._build_left_panel(left)
        self._build_viewer_panel(right)

    def _build_left_panel(self, parent: Any) -> None:
        ctk = self._ctk

        # Header
        header = ctk.CTkLabel(
            parent,
            text="TrimTokens",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        header.pack(pady=(8, 2))

        subtitle = ctk.CTkLabel(
            parent,
            text="Documents → Markdown compact pour LLM",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
        )
        subtitle.pack(pady=(0, 10))

        # Drop zone
        self.drop_frame = ctk.CTkFrame(
            parent,
            height=120,
            fg_color=("gray90", "gray22"),
            corner_radius=14,
            border_width=2,
            border_color=("gray70", "gray40"),
        )
        self.drop_frame.pack(fill="x", padx=10, pady=6)
        self.drop_frame.pack_propagate(False)

        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text="📂  Glissez vos fichiers ici\n(ou cliquez pour parcourir)",
            font=ctk.CTkFont(size=14),
            justify="center",
        )
        self.drop_label.pack(expand=True)

        for widget in (self.drop_frame, self.drop_label):
            widget.bind("<Button-1>", lambda _e: self._browse_files())

        # Options
        options = ctk.CTkFrame(parent, fg_color="transparent")
        options.pack(fill="x", padx=8, pady=(6, 4))

        lang_label = ctk.CTkLabel(
            options,
            text="Langues OCR :",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        lang_label.grid(row=0, column=0, sticky="w", padx=(4, 8), pady=4)

        self.lang_vars: dict[str, Any] = {}
        for idx, (label, code) in enumerate(SUPPORTED_LANGUAGES):
            var = ctk.BooleanVar(value=code in {"fra", "eng"})
            self.lang_vars[code] = var
            cb = ctk.CTkCheckBox(options, text=label, variable=var)
            cb.grid(row=0, column=idx + 1, padx=3, pady=4, sticky="w")

        self.aggressive_var = ctk.BooleanVar(value=False)
        self.clipboard_var = ctk.BooleanVar(value=False)
        self.open_after_var = ctk.BooleanVar(value=False)
        self.force_ocr_var = ctk.BooleanVar(value=False)
        self.smart_filter_var = ctk.BooleanVar(value=False)

        ctk.CTkCheckBox(options, text="Mode agressif", variable=self.aggressive_var).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=4, pady=2
        )
        ctk.CTkCheckBox(options, text="Forcer OCR", variable=self.force_ocr_var).grid(
            row=1, column=2, sticky="w", padx=3, pady=2
        )
        ctk.CTkCheckBox(options, text="Presse-papiers", variable=self.clipboard_var).grid(
            row=1, column=3, sticky="w", padx=3, pady=2
        )
        ctk.CTkCheckBox(options, text="Ouvrir après", variable=self.open_after_var).grid(
            row=1, column=4, sticky="w", padx=3, pady=2
        )
        ctk.CTkCheckBox(
            options,
            text="🧠 Filtre intelligent (TOC/biblio/éparses)",
            variable=self.smart_filter_var,
        ).grid(row=2, column=0, columnspan=5, sticky="w", padx=4, pady=2)

        # Progress
        self.progress = ctk.CTkProgressBar(parent)
        self.progress.set(0.0)
        self.progress.pack(fill="x", padx=10, pady=(12, 4))

        self.status_label = ctk.CTkLabel(
            parent,
            text="Prêt. Glissez ou parcourez pour commencer.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
        )
        self.status_label.pack(pady=2)

        # Journal
        log_header = ctk.CTkLabel(
            parent,
            text="Journal  (double-clic sur une ligne pour visualiser)",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        log_header.pack(anchor="w", padx=12, pady=(10, 0))

        self.log_text = ctk.CTkTextbox(parent, height=180, font=ctk.CTkFont(size=11))
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(2, 8))
        self.log_text.bind("<Double-Button-1>", self._on_log_double_click)

        # Footer
        footer = ctk.CTkFrame(parent, fg_color="transparent")
        footer.pack(fill="x", padx=10, pady=(4, 6))

        self.recap_label = ctk.CTkLabel(
            footer,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
        )
        self.recap_label.pack(side="left", padx=2)

        self.open_dir_btn = ctk.CTkButton(
            footer,
            text="📁 Ouvrir dossier de sortie",
            command=self._open_output_dir,
            state="disabled",
            width=190,
        )
        self.open_dir_btn.pack(side="right")

    def _build_viewer_panel(self, parent: Any) -> None:
        """Visionneuse Markdown du fichier de sortie (panneau droit)."""
        ctk = self._ctk

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        viewer_header = ctk.CTkLabel(
            parent,
            text="Visionneuse Markdown",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        viewer_header.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 2))

        self.viewer_file_label = ctk.CTkLabel(
            parent,
            text="Aucun fichier sélectionné.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"),
            anchor="w",
        )
        self.viewer_file_label.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))

        self.viewer_text = ctk.CTkTextbox(
            parent,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word",
        )
        self.viewer_text.grid(row=2, column=0, sticky="nsew", padx=10, pady=4)
        self.viewer_text.insert(
            "end",
            "Le contenu du dernier fichier .clean.md s'affichera ici "
            "après traitement.\n\nDouble-cliquez sur une ligne du journal "
            "pour visualiser un autre fichier de la liste.",
        )
        self.viewer_text.configure(state="disabled")

        viewer_buttons = ctk.CTkFrame(parent, fg_color="transparent")
        viewer_buttons.grid(row=3, column=0, sticky="ew", padx=10, pady=(4, 10))

        self.viewer_copy_btn = ctk.CTkButton(
            viewer_buttons,
            text="📋 Copier",
            width=110,
            command=self._copy_viewer_to_clipboard,
            state="disabled",
        )
        self.viewer_copy_btn.pack(side="left", padx=(4, 6))

        self.viewer_open_btn = ctk.CTkButton(
            viewer_buttons,
            text="📝 Ouvrir dans éditeur",
            width=180,
            command=self._open_viewer_file,
            state="disabled",
        )
        self.viewer_open_btn.pack(side="left", padx=2)

        self.viewer_refresh_btn = ctk.CTkButton(
            viewer_buttons,
            text="🔄 Recharger",
            width=110,
            command=self._refresh_viewer,
            state="disabled",
        )
        self.viewer_refresh_btn.pack(side="right", padx=4)

    def _setup_drop_target(self) -> None:
        self.drop_frame.drop_target_register(self._DND_FILES)
        self.drop_frame.dnd_bind("<<Drop>>", self._on_drop)

    # ------------------------------------------------------------------
    # Handlers (events View → controller logic)
    # ------------------------------------------------------------------

    def _on_drop(self, event: Any) -> None:
        if self.state.processing:
            self._log("Traitement en cours. Patientez.")
            return
        paths = _parse_dropped_paths(event.data)
        self._enqueue_paths(paths)

    def _browse_files(self) -> None:
        if self.state.processing:
            return
        from tkinter import filedialog

        files = filedialog.askopenfilenames(
            title="Sélectionner les fichiers à traiter",
            filetypes=[
                (
                    "Tous les formats supportés",
                    "*.pdf *.docx *.pptx *.xlsx *.csv *.html *.htm *.txt *.md *.rtf "
                    "*.png *.jpg *.jpeg *.webp *.tiff *.bmp",
                ),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if files:
            self._enqueue_paths([Path(f) for f in files])

    def _enqueue_paths(self, paths: list[Path]) -> None:
        from trimtokens.extractors import EXTENSION_MAP

        extensions = set(EXTENSION_MAP.keys())
        files: list[Path] = []

        for p in paths:
            if not p.exists():
                self._log(f"Ignoré (introuvable) : {p}")
                continue
            if p.is_file():
                if p.suffix.lower() in extensions:
                    files.append(p)
                else:
                    self._log(f"Ignoré (format non supporté) : {p.name}")
            elif p.is_dir():
                count_before = len(files)
                for child in sorted(p.rglob("*")):
                    if child.is_file() and child.suffix.lower() in extensions:
                        files.append(child)
                self._log(f"Dossier {p.name} : {len(files) - count_before} fichier(s) ajouté(s)")

        if not files:
            self._log("Aucun fichier supporté trouvé.")
            return

        self._log(f"--- Traitement de {len(files)} fichier(s) ---")
        self.state.processing = True
        self.state.reset_batch()

        options = self._build_options()
        callbacks = ProcessingCallbacks(
            on_progress=self._update_progress,
            on_file_success=self._on_file_success,
            on_file_failure=self._on_file_failure,
            on_complete=self._on_batch_complete,
        )
        self.service.start(files, options, callbacks)

    def _build_options(self) -> ExtractOptions:
        languages = "+".join(code for code, var in self.lang_vars.items() if var.get())
        if not languages:
            languages = "fra+eng"
        return ExtractOptions(
            ocr_languages=languages,
            aggressive=self.aggressive_var.get(),
            force_ocr=self.force_ocr_var.get(),
            smart_filter=self.smart_filter_var.get(),
        )

    # ------------------------------------------------------------------
    # Service callbacks (sur thread Tk via dispatch)
    # ------------------------------------------------------------------

    def _on_file_success(
        self, file_path: Path, result: ProcessResult, duration: float, entry: FileResult
    ) -> None:
        self.state.results.append(entry)
        s = result.stats
        target = entry.target
        target_name = target.name if target is not None else "?"
        msg = (
            f"✓ {file_path.name} → {target_name}\n"
            f"    Taille       : {_format_bytes(s.original_size_bytes)} → "
            f"{_format_bytes(s.cleaned_size_bytes)}  "
            f"({-s.reduction_percent:+.1f} %)\n"
            f"    Tokens brut  : ~{_format_count(s.tokens_input_estimated)} → "
            f"~{_format_count(s.tokens_estimated)}  "
            f"({-s.tokens_input_reduction_percent:+.1f} %)\n"
            f"    Tokens texte : ~{_format_count(s.tokens_original_estimated)} → "
            f"~{_format_count(s.tokens_estimated)}  "
            f"({-s.tokens_reduction_percent:+.1f} %)\n"
            f"    Durée        : {duration:.1f}s"
        )
        self._log(msg, target)

        # Avertissement PDF image-based sans OCR effectif
        if (
            result.document.metadata.get("image_based")
            and not result.document.ocr_used
        ):
            metrics = result.document.metadata.get("image_based_metrics", {})
            avg_chars = metrics.get("avg_chars_per_page", 0) if isinstance(metrics, dict) else 0
            avg_images = metrics.get("avg_images_per_page", 0) if isinstance(metrics, dict) else 0
            warn = (
                f"⚠  {file_path.name} semble image-based "
                f"({avg_chars:.0f} chars/page, {avg_images:.1f} images/page).\n"
                f"    Installer Tesseract pour extraire le contenu via OCR :\n"
                f"    winget install --id UB-Mannheim.TesseractOCR\n"
                f"    Puis relancer avec l'option « Forcer OCR » cochée."
            )
            self._log(warn)

    def _on_file_failure(self, file_path: Path, exc: Exception, entry: FileResult) -> None:
        self.state.results.append(entry)
        self._log(f"✗ {file_path.name} : {exc}")

    def _on_batch_complete(self, last_output_path: Path | None, last_output_text: str) -> None:
        if last_output_path is not None:
            self.state.output_dir = last_output_path.parent
            self._enable_open_button()
            self._show_in_viewer(last_output_path)

            if self.clipboard_var.get() and last_output_text:
                self._copy_to_clipboard(last_output_text)
            if self.open_after_var.get():
                _open_in_explorer(last_output_path)

        self._update_recap()
        self.state.processing = False

    # ------------------------------------------------------------------
    # Helpers View (mutations widgets)
    # ------------------------------------------------------------------

    def _dispatch(self, func: Any, *args: Any) -> None:
        """Schedule un callback dans le thread Tk (utilisé par `ProcessingService`)."""
        self.root.after(0, func, *args)

    def _update_progress(self, value: float, status: str) -> None:
        self.progress.set(value)
        self.status_label.configure(text=status)

    def _log(self, message: str, target: Path | None = None) -> None:
        # Capture la ligne courante AVANT insertion (1-based dans Tk text).
        current_line = int(self.log_text.index("end-1c").split(".")[0])
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        if target is not None:
            self.state.log_line_targets[current_line] = target

    def _on_log_double_click(self, _event: Any) -> None:
        try:
            line_index = self.log_text.index("insert")
            line_no = int(line_index.split(".")[0])
        except (ValueError, AttributeError):
            return
        target = self.state.log_line_targets.get(line_no)
        if target is not None and target.exists():
            self._show_in_viewer(target)

    def _show_in_viewer(self, path: Path) -> None:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            content = f"[Erreur lecture] {exc}"

        self.state.current_viewer_path = path
        self.viewer_file_label.configure(text=f"📄 {path.name}")
        self.viewer_text.configure(state="normal")
        self.viewer_text.delete("1.0", "end")
        self.viewer_text.insert("1.0", content)
        self.viewer_text.configure(state="disabled")
        self.viewer_text.see("1.0")

        self.viewer_copy_btn.configure(state="normal")
        self.viewer_open_btn.configure(state="normal")
        self.viewer_refresh_btn.configure(state="normal")

    def _copy_viewer_to_clipboard(self) -> None:
        content = self.viewer_text.get("1.0", "end-1c")
        if not content.strip():
            return
        try:
            import pyperclip  # type: ignore[import-untyped]

            pyperclip.copy(content)
            self._log("Contenu de la visionneuse copié dans le presse-papiers.")
        except Exception as exc:
            self._log(f"Clipboard indisponible : {exc}")

    def _open_viewer_file(self) -> None:
        if self.state.current_viewer_path is not None:
            _open_in_explorer(self.state.current_viewer_path)

    def _refresh_viewer(self) -> None:
        if self.state.current_viewer_path is not None and self.state.current_viewer_path.exists():
            self._show_in_viewer(self.state.current_viewer_path)

    def _enable_open_button(self) -> None:
        self.open_dir_btn.configure(state="normal")

    def _update_recap(self) -> None:
        if not self.state.results:
            return
        successes = sum(1 for r in self.state.results if r.status == "✓")
        total_before = sum(r.size_before for r in self.state.results)
        total_after = sum(r.size_after for r in self.state.results)
        tokens_before = sum(r.tokens_before for r in self.state.results)
        tokens_after = sum(r.tokens_after for r in self.state.results)
        size_gain = round((1 - total_after / total_before) * 100, 1) if total_before > 0 else 0
        tok_gain = (
            round((1 - tokens_after / tokens_before) * 100, 1) if tokens_before > 0 else 0
        )
        self.recap_label.configure(
            text=(
                f"{successes}/{len(self.state.results)} OK  •  "
                f"Taille {_format_bytes(total_before)} → {_format_bytes(total_after)} "
                f"(-{size_gain} %)  •  "
                f"Tokens brut ~{_format_count(tokens_before)} → ~{_format_count(tokens_after)} "
                f"(-{tok_gain} %)"
            )
        )

    def _copy_to_clipboard(self, text: str) -> None:
        try:
            import pyperclip  # type: ignore[import-untyped]

            pyperclip.copy(text)
            self._log("Copié dans le presse-papiers.")
        except Exception as exc:
            self._log(f"Clipboard indisponible : {exc}")

    def _open_output_dir(self) -> None:
        if self.state.output_dir is not None:
            _open_in_explorer(self.state.output_dir)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    """Entry point GUI."""
    try:
        gui = TrimTokensGUI()
    except ImportError as exc:
        print(f"Erreur d'import GUI : {exc}", file=sys.stderr)
        print(
            "Dépendances manquantes. Installer avec :\n  pip install trimtokens[gui]",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"Erreur au démarrage GUI : {exc}", file=sys.stderr)
        sys.exit(2)
    gui.run()


__all__ = ["TrimTokensGUI", "main"]
