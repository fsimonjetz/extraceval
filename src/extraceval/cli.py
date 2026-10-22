import logging
import webbrowser
from collections import defaultdict
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress
from rich.table import Table

from extraceval import extractors
from extraceval.compare import SimilarityMatrix, compare, similarity_matrix
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


@app.command("compare")
def compare_outputs(
    run: Annotated[Path, typer.Argument(help="Run directory, e.g. runs/my-run.")],
    names: Annotated[
        list[str] | None,
        typer.Argument(
            metavar="[EXTRACTORS]...",
            help="Two for a side-by-side diff; none (all) or three or more for a matrix.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Default: <run>/compare/<left>-vs-<right>.html"),
    ] = None,
    open_: Annotated[bool, typer.Option("--open", help="Open the report in a browser.")] = False,
) -> None:
    """Diff two extractors side by side in HTML, or print how similar all of them are."""
    names = names or []
    if len(names) == 1:
        _fail("give two extractors for a diff, or none or three or more for a matrix")

    if len(names) == 2:
        left, right = names
        try:
            path = compare(run, left, right, output)
        except ValueError as exc:
            _fail(str(exc))
        console.print(f"Comparison written to [bold]{path}[/]")
        if open_:
            webbrowser.open(path.resolve().as_uri())
        return

    try:
        matrix = similarity_matrix(run, names or None)
    except ValueError as exc:
        _fail(str(exc))
    console.print(_matrix_table(matrix))
    pairs = matrix.ranked_pairs()
    if len(pairs) > 1:
        console.print(f"Most similar:  {pairs[0][0]} / {pairs[0][1]} ({pairs[0][2]:.0%})")
        console.print(f"Least similar: {pairs[-1][0]} / {pairs[-1][1]} ({pairs[-1][2]:.0%})")
    left, right, _ = pairs[-1]
    console.print(f"[dim]Inspect a pair with: extraceval compare {run} {left} {right} --open[/]")


@app.command("list")
def list_extractors() -> None:
    """Show known extractors and whether they are installed."""
    table = Table("extractor", "package", "version", "options")
    for name, cls in extractors.registry().items():
        version = cls.version() or "[dim]not installed[/]"
        options = ", ".join(cls.options_model.model_fields) or "-"
        table.add_row(name, cls.distribution, version, options)
    console.print(table)


def _fail(message: str) -> NoReturn:
    console.print(f"[red]error:[/] {message}")
    raise typer.Exit(1)


def _matrix_table(matrix: SimilarityMatrix) -> Table:
    """Word-level similarity per pair, coloured relative to the range of scores."""
    scores = list(matrix.scores.values())
    low, high = min(scores), max(scores)

    def cell(value: float) -> str:
        position = (value - low) / (high - low) if high > low else 1.0
        colour = "green" if position > 2 / 3 else "yellow" if position > 1 / 3 else "red"
        return f"[{colour}]{value:.0%}[/]"

    table = Table("", *matrix.extractors, "mean", title="Similarity of extracted text")
    for row in matrix.extractors:
        cells = [
            "[dim]-[/]" if row == column else cell(matrix[row, column])
            for column in matrix.extractors
        ]
        table.add_row(row, *cells, f"[bold]{matrix.agreement(row):.0%}[/]")
    return table


def _summary(results: list[ExtractionResult]) -> Table:
    by_extractor: dict[str, list[ExtractionResult]] = defaultdict(list)
    for result in results:
        by_extractor[result.extractor].append(result)

    table = Table("extractor")
    for column in ("ok", "errors", "pages", "total s", "s / doc", "ms / page", "chars"):
        table.add_column(column, justify="right")
    for name, rows in by_extractor.items():
        ok = [r for r in rows if r.status == "ok"]
        seconds = sum(r.seconds for r in ok)
        pages = sum(r.pages for r in ok)
        table.add_row(
            name,
            str(len(ok)),
            str(len(rows) - len(ok)),
            f"{pages:,}",
            f"{seconds:.2f}",
            f"{seconds / len(ok):.3f}" if ok else "-",
            f"{1000 * seconds / pages:.1f}" if pages else "-",
            f"{sum(r.chars for r in ok):,}",
        )
    return table
