import logging
from collections import defaultdict
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress
from rich.table import Table

from extraceval import extractors
from extraceval.config import ConfigError, load_config
from extraceval.models import ExtractionResult
from extraceval.runner import Runner

app = typer.Typer(no_args_is_help=True, help="Compare PDF-to-text tools on your own documents.")
console = Console()


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False)],
    )


@app.command()
def run(
    input: Annotated[
        Path | None, typer.Argument(help="PDF file or directory. Overrides the config.")
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Config file. Default: ./extraceval.toml if present."),
    ] = None,
    sample: Annotated[int | None, typer.Option("--sample", "-n", min=1)] = None,
    seed: Annotated[int | None, typer.Option()] = None,
    extractor: Annotated[
        list[str] | None,
        typer.Option("--extractor", "-e", help="Extractor to run; repeatable. Default: all."),
    ] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    name: Annotated[
        str | None, typer.Option(help="Run name. Re-using one resumes that run.")
    ] = None,
    force: Annotated[bool, typer.Option(help="Re-run pairs that already succeeded.")] = False,
) -> None:
    """Run extractors over a sample of PDFs and save their outputs."""
    try:
        cfg = load_config(config).override(
            input=input, sample=sample, seed=seed, extractors=extractor, output=output
        )
        runner = Runner(cfg, name=name, force=force)
    except (ConfigError, FileNotFoundError) as exc:
        console.print(f"[red]error:[/] {exc}")
        raise typer.Exit(1) from None

    if not runner.extractors:
        console.print("[red]error:[/] none of the selected extractors is installed")
        raise typer.Exit(1)
    console.print(
        f"Running {len(runner.extractors)} extractor(s) on {len(runner.documents)} document(s)"
    )
    with Progress(console=console, transient=True) as progress:
        task = progress.add_task("Extracting", total=runner.total)
        result = runner.run(on_result=lambda _: progress.advance(task))

    console.print(_summary(result.results))
    console.print(f"Outputs written to [bold]{result.path}[/]")


@app.command("list")
def list_extractors() -> None:
    """Show known extractors and whether they are installed."""
    table = Table("extractor", "package", "version", "options")
    for name, cls in extractors.registry().items():
        version = cls.version() or "[dim]not installed[/]"
        options = ", ".join(cls.options_model.model_fields) or "-"
        table.add_row(name, cls.distribution, version, options)
    console.print(table)


def _summary(results: list[ExtractionResult]) -> Table:
    by_extractor: dict[str, list[ExtractionResult]] = defaultdict(list)
    for result in results:
        by_extractor[result.extractor].append(result)

    table = Table("extractor", "ok", "errors", "total s", "s / doc", "chars")
    for name, rows in by_extractor.items():
        ok = [r for r in rows if r.status == "ok"]
        seconds = sum(r.seconds for r in ok)
        table.add_row(
            name,
            str(len(ok)),
            str(len(rows) - len(ok)),
            f"{seconds:.2f}",
            f"{seconds / len(ok):.3f}" if ok else "-",
            f"{sum(r.chars for r in ok):,}",
        )
    return table
