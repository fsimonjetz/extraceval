"""Page-wise, line-aligned diffs of two extraction outputs, with word-level highlights.

Whitespace is normalised before diffing: runs of spaces collapse to one and blank lines are
dropped, since tools differ in spacing far more than in content. Similarity is computed on the
word sequence of a page, so it is not affected by where the tools break lines.
"""

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from itertools import zip_longest
from typing import Literal

type Kind = Literal["equal", "delete", "insert", "replace"]


@dataclass(frozen=True)
class Segment:
    text: str
    changed: bool = False


@dataclass(frozen=True)
class Line:
    number: int
    """1-based position among the page's normalised lines."""
    segments: tuple[Segment, ...]


@dataclass(frozen=True)
class Row:
    kind: Kind
    left: Line | None
    right: Line | None


@dataclass(frozen=True)
class PageDiff:
    number: int
    rows: list[Row]
    matched_words: int
    total_words: int

    @property
    def similarity(self) -> float:
        return 2 * self.matched_words / self.total_words if self.total_words else 1.0

    @property
    def identical(self) -> bool:
        return all(row.kind == "equal" for row in self.rows)


@dataclass(frozen=True)
class DocumentDiff:
    document: str
    pages: list[PageDiff] = field(default_factory=list)

    @property
    def similarity(self) -> float:
        total = sum(page.total_words for page in self.pages)
        matched = sum(page.matched_words for page in self.pages)
        return 2 * matched / total if total else 1.0


def normalize(text: str) -> list[str]:
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def diff_document(document: str, left: list[str], right: list[str]) -> DocumentDiff:
    """Diff two outputs page by page. A page missing on one side is diffed against nothing."""
    pages = [
        diff_page(number, a, b)
        for number, (a, b) in enumerate(zip_longest(left, right, fillvalue=""), start=1)
    ]
    return DocumentDiff(document, pages)


def diff_page(number: int, left: str, right: str) -> PageDiff:
    a, b = normalize(left), normalize(right)
    rows: list[Row] = []
    for kind, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if kind == "equal":
            rows += [
                Row("equal", _line(i + 1, a[i]), _line(j + 1, b[j]))
                for i, j in zip(range(i1, i2), range(j1, j2), strict=True)
            ]
        elif kind == "delete":
            rows += [Row("delete", _line(i + 1, a[i], changed=True), None) for i in range(i1, i2)]
        elif kind == "insert":
            rows += [Row("insert", None, _line(j + 1, b[j], changed=True)) for j in range(j1, j2)]
        else:
            for i, j in zip_longest(range(i1, i2), range(j1, j2)):
                if i is None:
                    rows.append(Row("insert", None, _line(j + 1, b[j], changed=True)))
                elif j is None:
                    rows.append(Row("delete", _line(i + 1, a[i], changed=True), None))
                else:
                    rows.append(Row("replace", *_word_diff(i + 1, a[i], j + 1, b[j])))

    return PageDiff(number, rows, *word_overlap(left, right))


def word_overlap(left: str, right: str) -> tuple[int, int]:
    """Words the two texts have in common, in order, and their total word count.

    Similarity is ``2 * matched / total``; whitespace and line breaks do not affect it.
    """
    words_a, words_b = left.split(), right.split()
    matcher = SequenceMatcher(None, words_a, words_b, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return matched, len(words_a) + len(words_b)


def _line(number: int, text: str, changed: bool = False) -> Line:
    return Line(number, (Segment(text, changed),))


def _word_diff(number_a: int, a: str, number_b: int, b: str) -> tuple[Line, Line]:
    """Two lines with the words that differ between them marked as changed."""
    words_a, words_b = a.split(" "), b.split(" ")
    left: list[Segment] = []
    right: list[Segment] = []
    for kind, i1, i2, j1, j2 in SequenceMatcher(
        None, words_a, words_b, autojunk=False
    ).get_opcodes():
        changed = kind != "equal"
        if i1 < i2:
            left.append(Segment(" ".join(words_a[i1:i2]), changed))
        if j1 < j2:
            right.append(Segment(" ".join(words_b[j1:j2]), changed))
    return Line(number_a, _join(left)), Line(number_b, _join(right))


def _join(segments: list[Segment]) -> tuple[Segment, ...]:
    """Put the spaces between words back, outside the highlighted spans."""
    joined: list[Segment] = []
    for segment in segments:
        if joined:
            joined.append(Segment(" "))
        joined.append(segment)
    return tuple(joined)
