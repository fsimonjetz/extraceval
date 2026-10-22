import logging
import sys
import webbrowser
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich import box
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress
from rich.table import Table

from extraceval import extractors
from extraceval.compare import Metric, SimilarityMatrix, compare, similarity_matrix
from extraceval.config import ConfigError, load_config
from extraceval.runner import Runner
from extraceval.summary import ExtractorSummary, summarize

app = typer.Typer(no_args_is_help=True, help="Compare PDF-to-text tools on your own documents.")
console = Console()

UNITS = {Metric.WORDS: "words", Metric.NGRAMS: "3-word sequences"}
"""What the directional matrix metrics count, for titles and summaries."""


@app.callback()
def main(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Also show the tools' own log messages.")
    ] = False,
) -> None:
    # Pin the console to the current stdout; during extraction, sys.stdout points at the tool log.
    console.file = sys.stdout
    # By default only extraceval's own messages reach the terminal; the tools' go to tools.log.
    logger = logging.getLogger() if verbose else logging.getLogger("extraceval")
    for existing in (logging.getLogger(), logging.getLogger("extraceval")):
        for handler in [h for h in existing.handlers if isinstance(h, RichHandler)]:
            existing.removeHandler(handler)
    logger.addHandler(RichHandler(console=console, show_path=False))
    logger.setLevel(logging.DEBUG if verbose else logging.WARNING)


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

    console.print(_summary_table(summarize(result.path, [s.name for s in runner.extractors])))
    console.print(f"Outputs written to [bold]{result.path}[/]")
    if result.tool_log:
        console.print(f"[dim]Messages from the tools are in {result.tool_log}[/]")


@app.command("summary")
def show_summary(
    run: Annotated[Path, typer.Argument(help="Run directory, e.g. runs/my-run.")],
) -> None:
    """Show speed and success per extractor for an existing run."""
    summaries = summarize(run)
    if not summaries:
        _fail(f"no results in {run}")
    console.print(_summary_table(summaries))


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
    metric: Annotated[
        Metric,
        typer.Option(
            "--metric",
            "-m",
            help="Matrix metric: shared 3-word sequences (intact sentences), shared words "
            "(text present), or similarity including the order of blocks.",
        ),
    ] = Metric.NGRAMS,
) -> None:
    """Diff two extractors side by side in HTML, or print a matrix of how much they agree.

    The matrix shows how much of the column tool's text the row tool also has on the same
    page: as 3-word sequences by default, or as single words with --metric words. With
    --metric order it shows how similar the outputs are, including the order of blocks.
    """
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
        matrix = similarity_matrix(run, names or None, metric)
    except ValueError as exc:
        _fail(str(exc))
    speed = {s.extractor: s.pages_per_second for s in summarize(run, matrix.extractors)}
    console.print(_matrix_table(matrix, speed))

    pairs = matrix.ranked_pairs()
    if not pairs:
        hint = " Try --metric words." if matrix.metric == Metric.NGRAMS else ""
        console.print(f"[yellow]There is too little text to compare.{hint}[/]")
        return
    (a, b, high), (c, d, low) = pairs[0], pairs[-1]
    if len(pairs) > 1:
        if matrix.metric in UNITS:
            unit = UNITS[matrix.metric]
            console.print(f"Highest: {a} contains {high:.0%} of {b}'s {unit}")
            console.print(f"Lowest:  {c} contains {low:.0%} of {d}'s {unit}")
        else:
            console.print(f"Most similar:  {a} / {b} ({high:.0%})")
            console.print(f"Least similar: {c} / {d} ({low:.0%})")
    console.print(f"[dim]Inspect a pair with: extraceval compare {run} {c} {d} --open[/]")


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


def _matrix_table(matrix: SimilarityMatrix, speed: dict[str, float | None]) -> Table:
    """Scores per pair, coloured relative to their range, with each extractor's pages per
    second alongside to weigh agreement against speed."""
    scores = [score for score in matrix.scores.values() if score is not None]
    low, high = (min(scores), max(scores)) if scores else (0.0, 1.0)

    def cell(value: float | None) -> str:
        if value is None:
            return "[dim]n/a[/]"
        position = (value - low) / (high - low) if high > low else 1.0
        colour = "green" if position > 2 / 3 else "yellow" if position > 1 / 3 else "red"
        return f"[{colour}]{value:.0%}[/]"

    # Columns are numbered so that the table stays narrow with many or long names.
    names = matrix.extractors
    title = (
        f"Share of the column tool's {UNITS[matrix.metric]} that the row tool also has"
        if matrix.metric in UNITS
        else "Similarity of the word sequences, including the order of blocks"
    )
    table = Table(box=box.SIMPLE_HEAD, pad_edge=False, title=title)
    table.add_column("extractor", no_wrap=True)
    for number in range(1, len(names) + 1):
        table.add_column(str(number), justify="right", no_wrap=True)
    table.add_column("mean", justify="right", no_wrap=True)
    table.add_column("pages/s", justify="right", no_wrap=True)
    for number, row in enumerate(names, start=1):
        cells = ["[dim]-[/]" if row == column else cell(matrix[row, column]) for column in names]
        label = f"[dim]{number}[/] {row}"
        agreement = matrix.agreement(row)
        mean = f"[bold]{agreement:.0%}[/]" if agreement is not None else "[dim]n/a[/]"
        table.add_row(label, *cells, mean, _rate(speed.get(row)))
    return table


def _summary_table(summaries: list[ExtractorSummary]) -> Table:
    """Speed per extractor; ``ok`` shows successful of all documents, e.g. ``4/5``."""
    table = Table(box=box.SIMPLE_HEAD, pad_edge=False)
    width = max(len(s.extractor) for s in summaries)
    table.add_column("extractor", no_wrap=True, min_width=width)
    for column in ("ok", "pages", "pages/s", "s/doc", "total s", "setup s", "chars"):
        table.add_column(column, justify="right", no_wrap=True)
    for s in summaries:
        ok = f"{s.ok}/{s.ok + s.errors}"
        table.add_row(
            s.extractor,
            ok if not s.errors else f"[red]{ok}[/]",
            f"{s.pages:,}",
            _rate(s.pages_per_second),
            _seconds(s.seconds_per_document),
            _seconds(s.seconds),
            _seconds(s.setup_seconds),
            f"{s.chars:,}",
        )
    return table


def _rate(value: float | None) -> str:
    """Whole numbers for fast tools, decimals for slow ones: 4,164 / 51 / 7.3 / 0.25."""
    if value is None:
        return "-"
    if value >= 10:
        return f"{value:,.0f}"
    return f"{value:.1f}" if value >= 1 else f"{value:.2f}"


def _seconds(value: float | None) -> str:
    if value is None:
        return "-"
    if value >= 100:
        return f"{value:,.0f}"
    return f"{value:.2f}" if value >= 0.01 else "<0.01"
