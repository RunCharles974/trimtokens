"""CLI typer pour TrimTokens.

Interface en ligne de commande principale. Réutilise `core.process()` pour toute la
logique métier — la CLI gère uniquement l'I/O, l'affichage Rich et les flags.

Usage typique :
    trimtokens document.pdf
    trimtokens ./dossier/ --recursive --out ./clean/
    trimtokens document.pdf --stdout
    trimtokens document.pdf --clipboard
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from trimtokens import __version__
from trimtokens.config import load_config
from trimtokens.core import process
from trimtokens.exceptions import ConfigError
from trimtokens.extractors import EXTENSION_MAP
from trimtokens.logging_setup import setup_logging
from trimtokens.models import ExtractOptions, ProcessResult

app = typer.Typer(
    name="trimtokens",
    help="Convertit documents (PDF, DOCX, PPTX, XLSX, images, HTML) en Markdown compact "
    "pour réduire la consommation de tokens Claude.",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)

console = Console()
err_console = Console(stderr=True)
log = logging.getLogger("trimtokens")


# --- Helpers ----------------------------------------------------------------


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"trimtokens v{__version__}")
        raise typer.Exit()


def _setup_logging(quiet: bool, verbose: bool, json_file: Path | None = None) -> None:
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.ERROR
    else:
        level = logging.WARNING

    setup_logging(
        level=level,
        console=True,
        json_file=json_file,
        err_console=err_console,
    )


def _collect_input_files(path: Path, recursive: bool) -> list[Path]:
    """Collecte tous les fichiers supportés depuis un chemin (fichier ou dossier)."""
    extensions = set(EXTENSION_MAP.keys())

    if not path.exists():
        log.error("Chemin introuvable : %s", path)
        return []

    if path.is_file():
        return [path]

    if path.is_dir():
        pattern = "**/*" if recursive else "*"
        return [
            child
            for child in sorted(path.glob(pattern))
            if child.is_file() and child.suffix.lower() in extensions
        ]

    return []


def _format_bytes(n: int) -> str:
    value: float = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _format_number(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _chars_reduction_percent(original: int, cleaned: int) -> float:
    if original == 0:
        return 0.0
    return round((1 - cleaned / original) * 100, 2)


def _print_profile_table(result: ProcessResult) -> None:
    """Affiche le breakdown StepMetrics agrégé (flag CLI --profile)."""
    from trimtokens.cleaners.steps import StepMetrics

    metrics: list[StepMetrics] = [
        m for m in result.pipeline_metrics if isinstance(m, StepMetrics)
    ]
    if not metrics:
        console.print("[dim italic]Aucune métrique de pipeline disponible.[/dim italic]")
        return

    total_ms = sum(m.duration_ms for m in metrics)

    table = Table(
        show_header=True,
        header_style="bold magenta",
        title=f"Pipeline de nettoyage — {len(metrics)} étape(s), {total_ms:.2f} ms total",
        title_justify="left",
    )
    table.add_column("Étape", style="dim")
    table.add_column("Chars in", justify="right")
    table.add_column("Chars out", justify="right")
    table.add_column("Δ chars", justify="right", style="cyan")
    table.add_column("Δ %", justify="right", style="cyan")
    table.add_column("Temps (ms)", justify="right", style="green")
    table.add_column("% total", justify="right", style="green")

    for m in metrics:
        share = (m.duration_ms / total_ms * 100) if total_ms > 0 else 0.0
        table.add_row(
            m.name,
            _format_number(m.chars_in),
            _format_number(m.chars_out),
            f"-{_format_number(m.chars_removed)}",
            f"-{m.reduction_percent}%",
            f"{m.duration_ms:.3f}",
            f"{share:.1f}%",
        )

    console.print(table)


def _print_stats_table(
    file_path: Path, output_path: Path | None, result: ProcessResult, duration: float
) -> None:
    s = result.stats
    if output_path is not None:
        console.print(f"[green]✓[/green] {file_path.name} → {output_path}")

    table = Table(show_header=True, header_style="bold cyan", title_justify="left")
    table.add_column("Métrique", style="dim")
    table.add_column("Avant", justify="right")
    table.add_column("Après", justify="right")
    table.add_column("Gain", justify="right", style="green")

    table.add_row(
        "Taille",
        _format_bytes(s.original_size_bytes),
        _format_bytes(s.cleaned_size_bytes),
        f"-{s.reduction_percent} %",
    )
    table.add_row(
        "Caractères",
        _format_number(s.original_chars),
        _format_number(s.cleaned_chars),
        f"-{_chars_reduction_percent(s.original_chars, s.cleaned_chars)} %",
    )
    table.add_row(
        "Tokens (upload brut)",
        f"~{_format_number(s.tokens_input_estimated)}",
        f"~{_format_number(s.tokens_estimated)}",
        f"-{s.tokens_input_reduction_percent} %",
    )
    table.add_row(
        "Tokens (texte extrait)",
        f"~{_format_number(s.tokens_original_estimated)}",
        f"~{_format_number(s.tokens_estimated)}",
        f"-{s.tokens_reduction_percent} %",
    )
    if result.document.ocr_used:
        pages_str = ", ".join(str(p) for p in result.document.ocr_pages[:5])
        if len(result.document.ocr_pages) > 5:
            pages_str += "…"
        table.add_row("OCR", f"{len(result.document.ocr_pages)} page(s) [{pages_str}]", "—", "—")
    table.add_row("Durée", "—", f"{duration:.2f}s", "—")

    console.print(table)

    # Avertissement PDF image-based sans OCR effectif
    if result.document.metadata.get("image_based") and not result.document.ocr_used:
        console.print(
            "[yellow]⚠[/yellow]  [bold]PDF image-based détecté[/bold] mais OCR non appliqué.\n"
            "    Le contenu utile est dans les images du PDF. "
            "Installer Tesseract puis relancer avec [cyan]--force-ocr[/cyan] :\n"
            "    [dim]winget install --id UB-Mannheim.TesseractOCR[/dim]"
        )


def _render_output(result: ProcessResult, fmt: str) -> str:
    if fmt == "md":
        return result.markdown
    if fmt == "txt":
        parts: list[str] = []
        if result.document.title:
            parts.append(result.document.title)
        for section in result.document.sections:
            if section.header:
                parts.append(section.header)
            if section.content:
                parts.append(section.content)
        return "\n\n".join(parts) + "\n"
    if fmt == "json":
        data = {
            "source": result.document.source_path.name,
            "type": result.document.source_type,
            "title": result.document.title,
            "ocr_used": result.document.ocr_used,
            "ocr_pages": result.document.ocr_pages,
            "sections": [
                {"header": s.header, "content": s.content} for s in result.document.sections
            ],
            "stats": {
                "original_size_bytes": result.stats.original_size_bytes,
                "cleaned_size_bytes": result.stats.cleaned_size_bytes,
                "reduction_percent": result.stats.reduction_percent,
                "original_chars": result.stats.original_chars,
                "cleaned_chars": result.stats.cleaned_chars,
                "tokens_estimated": result.stats.tokens_estimated,
                "tokens_original_estimated": result.stats.tokens_original_estimated,
                "tokens_reduction_percent": result.stats.tokens_reduction_percent,
                "tokens_input_estimated": result.stats.tokens_input_estimated,
                "tokens_input_reduction_percent": result.stats.tokens_input_reduction_percent,
            },
        }
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    raise typer.BadParameter(f"Format inconnu : '{fmt}'. Attendu : md, txt, json.")


def _output_extension(fmt: str) -> str:
    return {"md": ".clean.md", "txt": ".clean.txt", "json": ".clean.json"}[fmt]


def _copy_to_clipboard(text: str) -> bool:
    """Tente la copie clipboard ; retourne True si succès."""
    try:
        import pyperclip  # type: ignore[import-untyped]

        pyperclip.copy(text)
        return True
    except Exception as exc:
        log.warning("Clipboard indisponible : %s", exc)
        return False


# --- Construction options (config TOML + CLI overrides) -------------------


def _build_options(
    *,
    ctx: typer.Context,
    config_path: Path | None,
    ocr_lang: str,
    ocr_psm: int,
    no_ocr: bool,
    force_ocr: bool,
    aggressive: bool,
    workers: int,
    no_cache: bool,
    max_chars: int,
    smart_filter: bool,
    keep_toc: bool,
    keep_bibliography: bool,
    keep_sparse: bool,
) -> ExtractOptions:
    """Construit `ExtractOptions` en empilant defaults → config TOML → flags CLI.

    Si `config_path` est None, on retombe sur le comportement historique :
    chaque flag CLI alimente directement `ExtractOptions`.

    Si `config_path` est fourni, on part de `config.to_extract_options()` puis
    on n'écrase un champ que si le flag CLI correspondant a été passé
    explicitement (détecté via `ctx.get_parameter_source`).
    """
    if config_path is None:
        return ExtractOptions(
            ocr_languages=ocr_lang,
            ocr_psm=ocr_psm,
            no_ocr=no_ocr,
            force_ocr=force_ocr,
            aggressive=aggressive,
            workers=workers,
            use_cache=not no_cache,
            max_chars=max_chars,
            smart_filter=smart_filter,
            filter_toc=not keep_toc,
            filter_bibliography=not keep_bibliography,
            filter_sparse=not keep_sparse,
        )

    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc

    options = cfg.to_extract_options()

    def _is_cli(name: str) -> bool:
        try:
            src = ctx.get_parameter_source(name)
        except Exception:
            return False
        return src is not None and src.name == "COMMANDLINE"

    if _is_cli("ocr_lang"):
        options.ocr_languages = ocr_lang
    if _is_cli("ocr_psm"):
        options.ocr_psm = ocr_psm
    if _is_cli("no_ocr"):
        options.no_ocr = no_ocr
    if _is_cli("force_ocr"):
        options.force_ocr = force_ocr
    if _is_cli("aggressive"):
        options.aggressive = aggressive
    if _is_cli("workers"):
        options.workers = workers
    if _is_cli("no_cache"):
        options.use_cache = not no_cache
    if _is_cli("max_chars"):
        options.max_chars = max_chars
    if _is_cli("smart_filter"):
        options.smart_filter = smart_filter
    if _is_cli("keep_toc"):
        options.filter_toc = not keep_toc
    if _is_cli("keep_bibliography"):
        options.filter_bibliography = not keep_bibliography
    if _is_cli("keep_sparse"):
        options.filter_sparse = not keep_sparse

    return options


# --- Commande principale ----------------------------------------------------


@app.command(name="trimtokens")
def main(
    ctx: typer.Context,
    path: Path | None = typer.Argument(
        None,
        help="Fichier ou dossier à traiter.",
        show_default=False,
    ),
    fmt: str = typer.Option(
        "md",
        "--format",
        "-f",
        help="Format de sortie : md, txt, json.",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        "-o",
        help="Dossier de sortie (défaut : à côté du fichier source).",
    ),
    stdout: bool = typer.Option(
        False,
        "--stdout",
        help="Écrire sur stdout au lieu d'un fichier.",
    ),
    clipboard: bool = typer.Option(
        False,
        "--clipboard",
        "-c",
        help="Copier le résultat dans le presse-papiers.",
    ),
    recursive: bool = typer.Option(
        False,
        "--recursive",
        "-r",
        help="Récursif pour les dossiers.",
    ),
    ocr_lang: str = typer.Option(
        "fra+eng",
        "--ocr-lang",
        help="Langues OCR Tesseract (ex : fra+eng, deu, spa+ita).",
    ),
    no_ocr: bool = typer.Option(
        False,
        "--no-ocr",
        help="Désactiver complètement OCR.",
    ),
    force_ocr: bool = typer.Option(
        False,
        "--force-ocr",
        help="Forcer OCR même si texte natif présent.",
    ),
    ocr_psm: int = typer.Option(
        6,
        "--ocr-psm",
        help="Tesseract Page Segmentation Mode (1=auto, 6=bloc, 11=épars).",
        min=0,
        max=13,
    ),
    max_chars: int = typer.Option(
        0,
        "--max-chars",
        help="Tronquer la sortie à N caractères (0 = pas de limite).",
        min=0,
    ),
    aggressive: bool = typer.Option(
        False,
        "--aggressive",
        "-a",
        help="Mode agressif : déduplication à partir de 2 occurrences.",
    ),
    smart_filter: bool = typer.Option(
        False,
        "--smart-filter",
        "-s",
        help="Filtrage intelligent : exclut TOC, bibliographie et pages éparses (PDF uniquement).",
    ),
    keep_toc: bool = typer.Option(
        False,
        "--keep-toc",
        help="Conserver la table des matières même si --smart-filter actif.",
    ),
    keep_bibliography: bool = typer.Option(
        False,
        "--keep-bibliography",
        help="Conserver la bibliographie même si --smart-filter actif.",
    ),
    keep_sparse: bool = typer.Option(
        False,
        "--keep-sparse",
        help="Conserver les pages éparses même si --smart-filter actif.",
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        help="Ignorer le cache OCR.",
    ),
    workers: int = typer.Option(
        0,
        "--workers",
        "-w",
        help="Nombre de workers parallèles OCR (0 = auto, cpu_count - 1).",
        min=0,
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Mode silencieux : pas de table de stats, erreurs seulement.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Mode verbeux : logs DEBUG.",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        help=(
            "Charger une configuration TOML. Les valeurs servent de defaults ; "
            "les flags CLI passés explicitement les surchargent."
        ),
        exists=False,
        dir_okay=False,
    ),
    log_file: Path | None = typer.Option(
        None,
        "--log-file",
        help=(
            "Écrire les événements structurés en JSON Lines dans ce fichier (append). "
            "Utile pour ingestion observabilité (Loki, ELK, jq)."
        ),
        dir_okay=False,
    ),
    profile: bool = typer.Option(
        False,
        "--profile",
        help="Affiche un tableau du temps passé par étape de nettoyage (StepMetrics).",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        help="Affiche la version et quitte.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Convertit documents → Markdown compact pour LLM."""
    if path is None:
        console.print(ctx.get_help())
        raise typer.Exit()

    effective_log_file = log_file
    if effective_log_file is None and config is not None:
        try:
            cfg_preview = load_config(config)
        except ConfigError:
            cfg_preview = None
        if cfg_preview is not None and cfg_preview.logging.json_file:
            effective_log_file = Path(cfg_preview.logging.json_file)

    _setup_logging(quiet=quiet, verbose=verbose, json_file=effective_log_file)

    if no_ocr and force_ocr:
        raise typer.BadParameter("--no-ocr et --force-ocr sont mutuellement exclusifs.")

    if fmt not in {"md", "txt", "json"}:
        raise typer.BadParameter(f"Format invalide : '{fmt}'. Attendu : md, txt, json.")

    if quiet and verbose:
        raise typer.BadParameter("--quiet et --verbose sont mutuellement exclusifs.")

    files = _collect_input_files(path, recursive=recursive)
    if not files:
        log.error("Aucun fichier supporté trouvé.")
        raise typer.Exit(code=1)

    if stdout and len(files) > 1:
        log.warning(
            "--stdout avec %d fichiers : seul le dernier sera lisible, les autres concaténés.",
            len(files),
        )

    options = _build_options(
        ctx=ctx,
        config_path=config,
        ocr_lang=ocr_lang,
        ocr_psm=ocr_psm,
        no_ocr=no_ocr,
        force_ocr=force_ocr,
        aggressive=aggressive,
        workers=workers,
        no_cache=no_cache,
        max_chars=max_chars,
        smart_filter=smart_filter,
        keep_toc=keep_toc,
        keep_bibliography=keep_bibliography,
        keep_sparse=keep_sparse,
    )

    out_dir: Path | None = None
    if out is not None:
        out_dir = out.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

    failure_count = 0
    last_output_text = ""

    for file_path in files:
        try:
            start = time.perf_counter()
            result = process(file_path, options)
            duration = time.perf_counter() - start

            output_text = _render_output(result, fmt)
            if max_chars > 0 and len(output_text) > max_chars:
                output_text = output_text[:max_chars]

            last_output_text = output_text

            if stdout:
                sys.stdout.write(output_text)
                if not output_text.endswith("\n"):
                    sys.stdout.write("\n")
                sys.stdout.flush()
                if not quiet:
                    _print_stats_table(file_path, None, result, duration)
                    if profile:
                        _print_profile_table(result)
            else:
                target_dir = out_dir or file_path.parent
                target_name = file_path.stem + _output_extension(fmt)
                target_path = target_dir / target_name
                target_path.write_text(output_text, encoding="utf-8")

                if not quiet:
                    _print_stats_table(file_path, target_path, result, duration)
                    if profile:
                        _print_profile_table(result)

        except Exception as exc:
            log.error("Échec sur %s : %s", file_path, exc)
            if verbose:
                log.exception("Détails :")
            failure_count += 1

    if clipboard and last_output_text and _copy_to_clipboard(last_output_text) and not quiet:
        console.print("[dim italic]Copié dans le presse-papiers.[/dim italic]")

    if failure_count > 0:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
