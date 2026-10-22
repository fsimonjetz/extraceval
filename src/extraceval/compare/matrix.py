"""Pairwise similarity of all extractors in a run, to see which agree and which stand out."""

from dataclasses import dataclass
from itertools import combinations, zip_longest
from pathlib import Path

from extraceval.compare.diff import word_overlap
from extraceval.storage import RunDirectory


@dataclass(frozen=True)
class SimilarityMatrix:
    extractors: list[str]
    scores: dict[tuple[str, str], float]
    """Word-level similarity per pair over all documents both extractors have outputs for."""

    def __getitem__(self, pair: tuple[str, str]) -> float:
        a, b = pair
        if a == b:
            return 1.0
        return self.scores[pair] if pair in self.scores else self.scores[b, a]

    def agreement(self, name: str) -> float:
        """Mean similarity of one extractor to all others."""
        others = [self[name, other] for other in self.extractors if other != name]
        return sum(others) / len(others) if others else 1.0

    def ranked_pairs(self) -> list[tuple[str, str, float]]:
        """All pairs, most similar first."""
        return sorted(((a, b, s) for (a, b), s in self.scores.items()), key=lambda p: -p[2])


def similarity_matrix(run: Path | str, extractors: list[str] | None = None) -> SimilarityMatrix:
    """Compare every pair of ``extractors`` (default: all in the run) on every document.

    Pages are aligned by position; the score weights each page by its number of words, so long
    pages count more than short ones.
    """
    directory = RunDirectory(Path(run))
    names = extractors or directory.extractors()
    directory.require_extractors(names)
    if len(names) < 2:
        raise ValueError("need at least two extractors to compare")

    matched = dict.fromkeys(combinations(names, 2), 0)
    total = dict.fromkeys(combinations(names, 2), 0)
    for document in directory.documents():
        pages = {
            name: directory.read_output(name, document)
            for name in names
            if directory.output_path(name, document).exists()
        }
        for a, b in matched:
            if a in pages and b in pages:
                for left, right in zip_longest(pages[a], pages[b], fillvalue=""):
                    m, t = word_overlap(left, right)
                    matched[a, b] += m
                    total[a, b] += t

    scores = {pair: 2 * matched[pair] / total[pair] if total[pair] else 1.0 for pair in matched}
    return SimilarityMatrix(list(names), scores)
