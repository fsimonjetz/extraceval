"""Static HTML side-by-side comparison of two extractors' outputs in a run."""

import re
import unicodedata
from dataclasses import dataclass
from html import escape
from importlib.resources import files
from pathlib import Path
from string import Template

from extraceval.compare.diff import DocumentDiff, Line, PageDiff, Row, diff_document
from extraceval.storage import RunDirectory

CONTEXT_LINES = 3
"""Unchanged lines shown around each change; longer unchanged stretches are folded."""

INVISIBLE = re.compile("[\u00ad\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]")
"""Format characters that render as nothing but make lines differ."""
INVISIBLE_LABELS = {
    "\u00ad": "SHY",
    "\u200b": "ZWSP",
    "\u200c": "ZWNJ",
    "\u200d": "ZWJ",
    "\u2060": "WJ",
    "\ufeff": "BOM",
}


@dataclass(frozen=True)
class DocumentComparison:
    document: str
    diff: DocumentDiff | None
    problem: str | None = None
    """Why there is no diff, e.g. an extractor failed on the document."""


def compare(run: Path | str, left: str, right: str, output: Path | str | None = None) -> Path:
    """Write an HTML diff of two extractors' outputs and return its path.

    The default location is ``<run>/compare/<left>-vs-<right>.html``.
    """
    directory = RunDirectory(Path(run))
    directory.require_extractors([left, right])
    errors = {(r.document, r.extractor): r.error for r in directory.read_results() if r.error}
    comparisons = [
        _compare_document(directory, doc, left, right, errors) for doc in directory.documents()
    ]
    path = Path(output) if output else directory.path / "compare" / f"{left}-vs-{right}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(directory.path.name, left, right, comparisons), encoding="utf-8")
    return path


def _compare_document(
    directory: RunDirectory,
    document: str,
    left: str,
    right: str,
    errors: dict[tuple[str, str], str],
) -> DocumentComparison:
    missing = [
        f"{name}: {errors.get((document, name)) or 'no output'}"
        for name in (left, right)
        if not directory.output_path(name, document).exists()
    ]
    if missing:
        return DocumentComparison(document, None, "; ".join(missing))
    pages_left = directory.read_output(left, document)
    pages_right = directory.read_output(right, document)
    return DocumentComparison(document, diff_document(document, pages_left, pages_right))


def render(run: str, left: str, right: str, comparisons: list[DocumentComparison]) -> str:
    ordered = sorted(
        comparisons, key=lambda c: (c.diff is not None, c.diff.similarity if c.diff else 0)
    )
    template = Template(files("extraceval.compare").joinpath("template.html").read_text("utf-8"))
    return template.substitute(
        title=escape(f"{left} vs {right} · {run}"),
        run=escape(run),
        left=escape(left),
        right=escape(right),
        overview=_overview(ordered),
        documents="\n".join(_document(c, left, right) for c in ordered),
    )


def _overview(comparisons: list[DocumentComparison]) -> str:
    rows = []
    for c in comparisons:
        link = f'<a href="#{_anchor(c.document)}">{escape(c.document)}</a>'
        if c.diff is None:
            problem = escape(c.problem or "")
            rows.append(f'<tr><td>{link}</td><td colspan="3" class="problem">{problem}</td></tr>')
            continue
        changed = sum(not page.identical for page in c.diff.pages)
        rows.append(
            f"<tr><td>{link}</td><td>{_percent(c.diff.similarity)}</td>"
            f"<td>{changed} / {len(c.diff.pages)}</td><td>{_bar(c.diff.similarity)}</td></tr>"
        )
    return "\n".join(rows)


def _document(c: DocumentComparison, left: str, right: str) -> str:
    anchor = _anchor(c.document)
    if c.diff is None:
        body = f'<p class="problem">{escape(c.problem or "")}</p>'
        summary = escape(c.document)
    else:
        body = "\n".join(_page(page, left, right) for page in c.diff.pages)
        summary = (
            f'{escape(c.document)} <span class="score">{_percent(c.diff.similarity)} similar</span>'
        )
    return (
        f'<details class="document" id="{anchor}" open><summary>{summary}</summary>{body}</details>'
    )


def _page(page: PageDiff, left: str, right: str) -> str:
    """A page section; identical pages start collapsed."""
    if page.identical:
        state, score = "", f"identical, {len(page.rows)} lines"
    else:
        state, score = " open", f"{_percent(page.similarity)} similar"
    summary = f'Page {page.number} <span class="score">{score}</span>'
    grid = _grid(page.rows, left, right)
    return f'<details class="page"{state}><summary>{summary}</summary>{grid}</details>'


def _grid(rows: list[Row], left: str, right: str) -> str:
    header = "".join(
        f'<div class="head"></div><div class="head">{escape(name)}</div>' for name in (left, right)
    )
    return f'<div class="diff">{header}{"".join(_folded(rows))}</div>'


def _folded(rows: list[Row]) -> list[str]:
    """Render rows, folding unchanged stretches away from changes into expandable blocks."""
    out: list[str] = []
    start = 0
    while start < len(rows):
        end = start
        while end < len(rows) and rows[end].kind == "equal":
            end += 1
        if end == start:
            out.append(_row(rows[start]))
            start += 1
            continue
        keep_head = CONTEXT_LINES if start > 0 else 0
        keep_tail = CONTEXT_LINES if end < len(rows) else 0
        run = rows[start:end]
        if len(run) - keep_head - keep_tail > CONTEXT_LINES:
            hidden = run[keep_head : len(run) - keep_tail]
            out += [_row(r) for r in run[:keep_head]]
            out.append(
                f'<details class="fold"><summary>{len(hidden)} unchanged lines</summary>'
                f'<div class="diff">{"".join(_row(r) for r in hidden)}</div></details>'
            )
            out += [_row(r) for r in run[len(run) - keep_tail :]]
        else:
            out += [_row(r) for r in run]
        start = end
    return out


def _row(row: Row) -> str:
    return _cells(row.left, "left", row.kind) + _cells(row.right, "right", row.kind)


def _cells(line: Line | None, side: str, kind: str) -> str:
    if line is None:
        return '<div class="num empty"></div><div class="text empty"></div>'
    css = f"{side} {kind}"
    text = "".join(
        f"<mark>{_visible(s.text)}</mark>" if s.changed and kind == "replace" else _visible(s.text)
        for s in line.segments
    )
    return f'<div class="num {css}">{line.number}</div><div class="text {css}">{text}</div>'


def _visible(text: str) -> str:
    """Escape text for HTML and show invisible format characters such as soft hyphens."""
    return INVISIBLE.sub(_marker, escape(text))


def _marker(match: re.Match[str]) -> str:
    char = match.group()
    label = INVISIBLE_LABELS.get(char, f"U+{ord(char):04X}")
    title = f"U+{ord(char):04X} {unicodedata.name(char, '')}"
    return f'<span class="invisible" title="{title}">{label}</span>'


def _anchor(document: str) -> str:
    return "doc-" + escape(document, quote=True)


def _percent(value: float) -> str:
    return f"{value:.0%}"


def _bar(value: float) -> str:
    return f'<span class="bar"><span style="width:{value * 100:.0f}%"></span></span>'
