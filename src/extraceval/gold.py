"""Scoring extractors against gold texts: clean articles copied from a press database.

Gold texts live in ``<gold>/<PDF file stem>/<label>.txt``, one article per file. The label is
usually the page the article starts on. Since the gold covers only some articles of an edition,
only recall is measured: how much of each article an extractor recovers, as words (is the text
there at all?) and as 3-word sequences (are the sentences intact?). Case is ignored, as print
headlines are often in capitals where the press database has them in mixed case.

Each article is located once for all extractors: on the pages where their outputs contain, on
average, at least ``LOCATE_THRESHOLD`` of the article's 3-word sequences. Every extractor is then
scored on those pages, so a weak extractor cannot shift the window in its favour, and an article
continued on later pages is found in full.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from extraceval.compare.matrix import NGRAM_SIZE, ngrams, words
from extraceval.storage import RunDirectory

LOCATE_THRESHOLD = 0.05


@dataclass(frozen=True)
class Article:
    document: str
    """Id of the run document the article belongs to."""
    name: str
    """``<PDF file stem>/<label>``, e.g. ``SPIEGEL_2026_37/13``."""
    words: list[str]

    @property
    def label(self) -> str:
        return self.name.rpartition("/")[2]

    @property
    def page(self) -> int | None:
        """The page the label names, if it is a number."""
        return int(self.label) if self.label.isdigit() else None


@dataclass(frozen=True)
class Score:
    words: float
    ngrams: float


@dataclass(frozen=True)
class ArticleResult:
    article: Article
    pages: list[int]
    """Pages (1-based) the article was located on; empty if it was not found."""
    scores: dict[str, Score]
    """By extractor, for those with an output for the article's document."""

    @property
    def misplaced(self) -> bool:
        """Whether the article was found, but not on the page its label names."""
        page = self.article.page
        return bool(self.pages) and page is not None and page not in self.pages


@dataclass(frozen=True)
class GoldReport:
    extractors: list[str]
    articles: list[ArticleResult]
    unmatched: list[str]
    """Gold folders without a document of that name in the run."""

    @property
    def found(self) -> list[ArticleResult]:
        return [result for result in self.articles if result.pages]

    def mean(self, extractor: str) -> Score | None:
        """Mean score over all found articles, each counting equally regardless of length."""
        scores = [r.scores[extractor] for r in self.found if extractor in r.scores]
        if not scores:
            return None
        return Score(
            words=sum(s.words for s in scores) / len(scores),
            ngrams=sum(s.ngrams for s in scores) / len(scores),
        )


def score(run: Path | str, gold: Path | str, extractors: list[str] | None = None) -> GoldReport:
    """Score ``extractors`` (default: all in the run) against the gold texts in ``gold``."""
    directory = RunDirectory(Path(run))
    gold = Path(gold)
    names = extractors or directory.extractors()
    directory.require_extractors(names)
    if not gold.is_dir():
        raise FileNotFoundError(f"gold directory not found: {gold}")

    documents = {
        Path(doc["source"]).stem: doc["id"]
        for doc in directory.read_manifest().get("documents", [])
    }
    folders = sorted(path for path in gold.iterdir() if path.is_dir())
    results = []
    for folder in folders:
        if folder.name not in documents:
            continue
        document = documents[folder.name]
        pages = {
            name: [tokens(page) for page in directory.read_output(name, document)]
            for name in names
            if directory.output_path(name, document).exists()
        }
        for path in sorted(folder.glob("*.txt"), key=_label_order):
            text = path.read_text(encoding="utf-8")
            article = Article(document, f"{folder.name}/{path.stem}", tokens(text))
            results.append(_score_article(article, pages))
    unmatched = [folder.name for folder in folders if folder.name not in documents]
    return GoldReport(list(names), results, unmatched)


def tokens(text: str) -> list[str]:
    return [word.casefold() for word in words(text)]


def _score_article(article: Article, pages: dict[str, list[list[str]]]) -> ArticleResult:
    gold_ngrams = ngrams(article.words, NGRAM_SIZE)
    located = _locate(gold_ngrams, pages)
    if not located:
        return ArticleResult(article, [], {})
    scores = {}
    gold_words = Counter(article.words)
    for name, tool_pages in pages.items():
        text = [
            word for page in located if page <= len(tool_pages) for word in tool_pages[page - 1]
        ]
        scores[name] = Score(
            words=_recall(gold_words, Counter(text)),
            ngrams=_recall(gold_ngrams, ngrams(text, NGRAM_SIZE)),
        )
    return ArticleResult(article, located, scores)


def _locate(gold: Counter[tuple[str, ...]], pages: dict[str, list[list[str]]]) -> list[int]:
    """Pages on which the extractors find, on average, a clear share of the article."""
    if not gold or not pages:
        return []
    count = max(len(tool_pages) for tool_pages in pages.values())
    located = []
    for index in range(count):
        recalls = [
            _recall(gold, ngrams(tool_pages[index], NGRAM_SIZE)) if index < len(tool_pages) else 0
            for tool_pages in pages.values()
        ]
        if sum(recalls) / len(recalls) >= LOCATE_THRESHOLD:
            located.append(index + 1)
    return located


def _recall[T](gold: Counter[T], found: Counter[T]) -> float:
    """Share of ``gold`` (counted with repetitions) that is also in ``found``."""
    return (gold & found).total() / gold.total() if gold else 0.0


def _label_order(path: Path) -> tuple[bool, int, str]:
    """Numbered pages first, in numeric order, then other labels such as ``e2``."""
    return (not path.stem.isdigit(), int(path.stem) if path.stem.isdigit() else 0, path.stem)


def page_ranges(pages: Iterable[int]) -> str:
    """``[6]`` -> ``6``, ``[10, 11, 12, 15]`` -> ``10-12, 15``."""
    ranges: list[list[int]] = []
    for page in sorted(pages):
        if ranges and page == ranges[-1][-1] + 1:
            ranges[-1].append(page)
        else:
            ranges.append([page])
    return ", ".join(str(r[0]) if len(r) == 1 else f"{r[0]}-{r[-1]}" for r in ranges)
