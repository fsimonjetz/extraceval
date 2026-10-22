"""Pairwise comparison of all extractors in a run, to see which agree and which stand out.

Three metrics, each computed per page and weighted over all documents:

- ``words`` (directional): the share of one extractor's words that another one also has on the
  same page, in any order. Does the text come out at all?
- ``ngrams`` (directional): the same for sequences of three consecutive words. Is the text in
  the right local order, with sentences intact? Unlike ``order``, it barely changes when two
  extractors put whole articles or blocks in a different order.
- ``order`` (symmetric): how similar the two word sequences are as a whole, so it also reflects
  whether the extractors agree on the reading order of blocks.

For the directional metrics, ``matrix[a, b]`` reads "a contains this much of b's text".

Words are compared after removing markup and punctuation and rejoining words hyphenated at line
breaks, so ``**Wort**``, ``<u>Wort</u>``, ``Wort,`` and ``Wo-`` + ``rt`` are all the same word.
"""

import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum
from itertools import combinations, permutations, zip_longest
from pathlib import Path

from extraceval.storage import RunDirectory

NGRAM_SIZE = 3

MARKUP = re.compile(r"<!--.*?-->|<[^>\n]+>", re.DOTALL)
SOFT_HYPHEN = "\N{SOFT HYPHEN}"
PDFIUM_HYPHEN = chr(0xFFFE)  # what PDFium puts in place of a hyphen at a line break
SOFT_BREAK = re.compile(rf"[{SOFT_HYPHEN}{PDFIUM_HYPHEN}]\s*")
HARD_BREAK = re.compile(r"(?<=[^\W\d_])-[ \t]*\n[ \t]*(?=[^\W\d_])")
WORD = re.compile(r"\w+")
NO_WORDS: list[str] = []


class Metric(StrEnum):
    WORDS = "words"
    NGRAMS = "ngrams"
    ORDER = "order"


@dataclass(frozen=True)
class SimilarityMatrix:
    extractors: list[str]
    metric: Metric
    scores: dict[tuple[str, str], float | None]
    """By ordered pair, or by unordered pair (stored once) for the symmetric ``order``.
    ``None`` where there is nothing to compare, e.g. the coverage of an empty output."""

    def __getitem__(self, pair: tuple[str, str]) -> float | None:
        a, b = pair
        if a == b:
            return 1.0
        return self.scores[pair] if pair in self.scores else self.scores[b, a]

    def agreement(self, name: str) -> float | None:
        """Mean score of one extractor against all others, as the row of the matrix."""
        others = [self[name, other] for other in self.extractors if other != name]
        defined = [score for score in others if score is not None]
        return sum(defined) / len(defined) if defined else None

    def ranked_pairs(self) -> list[tuple[str, str, float]]:
        """All pairs with a score, highest first."""
        scored = [(a, b, s) for (a, b), s in self.scores.items() if s is not None]
        return sorted(scored, key=lambda p: -p[2])


def words(text: str) -> list[str]:
    """The words of a text, without markup and punctuation, and with words that are hyphenated
    at a line break joined again.

    A soft hyphen (or PDFium's U+FFFE marker) always marks hyphenation, whether the tool kept
    the line break after it or replaced it with a space. A hard hyphen at the end of a line
    only counts as hyphenation if the next line continues in lower case, so ``Ge-`` +
    ``dächtnis`` is joined while ``KRIEGS-`` + ``FÜHRUNG`` and ``US-`` + ``Präsident`` stay
    separate words. Hard hyphens followed by a space are left alone, as in ``Ein- und Ausgang``.
    """
    text = MARKUP.sub(" ", text)
    text = SOFT_BREAK.sub("", text)
    text = HARD_BREAK.sub(_join_if_lowercase, text)
    return WORD.findall(text)


def _join_if_lowercase(match: re.Match[str]) -> str:
    return "" if match.string[match.end()].islower() else match.group()


def similarity_matrix(
    run: Path | str, extractors: list[str] | None = None, metric: Metric = Metric.NGRAMS
) -> SimilarityMatrix:
    """Compare every pair of ``extractors`` (default: all in the run) on every document.

    Pages are aligned by position, and only documents both extractors have outputs for count.
    """
    directory = RunDirectory(Path(run))
    names = extractors or directory.extractors()
    directory.require_extractors(names)
    if len(names) < 2:
        raise ValueError("need at least two extractors to compare")

    symmetric = metric == Metric.ORDER
    pairs = list(combinations(names, 2) if symmetric else permutations(names, 2))
    matched = dict.fromkeys(pairs, 0)
    total = dict.fromkeys(pairs, 0)
    for pages in _documents(directory, names):
        for a, b in pairs:
            if a not in pages or b not in pages:
                continue
            for left, right in zip_longest(pages[a], pages[b], fillvalue=NO_WORDS):
                if symmetric:
                    matcher = SequenceMatcher(None, left, right, autojunk=False)
                    common = sum(block.size for block in matcher.get_matching_blocks())
                    matched[a, b] += 2 * common
                    total[a, b] += len(left) + len(right)
                else:
                    size = NGRAM_SIZE if metric == Metric.NGRAMS else 1
                    ours, theirs = _ngrams(left, size), _ngrams(right, size)
                    matched[a, b] += sum((ours & theirs).values())
                    total[a, b] += theirs.total()

    scores = {pair: matched[pair] / total[pair] if total[pair] else None for pair in pairs}
    return SimilarityMatrix(list(names), metric, scores)


def _ngrams(words: list[str], size: int) -> Counter[tuple[str, ...]]:
    return Counter(zip(*(words[i:] for i in range(size)), strict=False))


def _documents(directory: RunDirectory, names: list[str]) -> Iterator[dict[str, list[list[str]]]]:
    """Per document, the words of each page for every extractor with an output for it."""
    for document in directory.documents():
        yield {
            name: [words(page) for page in directory.read_output(name, document)]
            for name in names
            if directory.output_path(name, document).exists()
        }
