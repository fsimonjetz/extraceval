from pathlib import Path

import pytest
from typer.testing import CliRunner

from extraceval import Config, Runner, compare
from extraceval.cli import app
from extraceval.compare import Metric, similarity_matrix
from extraceval.compare.diff import Segment, diff_document, diff_page, normalize
from extraceval.compare.matrix import PDFIUM_HYPHEN, SOFT_HYPHEN, words
from extraceval.models import ExtractionResult
from extraceval.storage import RunDirectory


def test_normalize_collapses_whitespace_and_drops_blank_lines() -> None:
    assert normalize("  a   b \n\n \t\nc\u00a0 d\n") == ["a b", "c d"]


def test_identical_page() -> None:
    page = diff_page(1, "a b\nc", "a  b\n\nc ")
    assert page.identical
    assert page.similarity == 1.0


def test_changed_words_are_marked() -> None:
    (row,) = diff_page(1, "the quick fox", "the quack fox").rows
    assert row.kind == "replace"
    assert row.left and row.right
    assert row.left.segments == (
        Segment("the"),
        Segment(" "),
        Segment("quick", True),
        Segment(" "),
        Segment("fox"),
    )
    assert Segment("quack", True) in row.right.segments


def test_inserted_and_deleted_lines() -> None:
    kinds = [row.kind for row in diff_page(1, "a\nb\nc", "a\nc\nd").rows]
    assert kinds == ["equal", "delete", "equal", "insert"]


def test_similarity_ignores_line_breaks() -> None:
    page = diff_page(1, "one two three four", "one two\nthree four")
    assert not page.identical
    assert page.similarity == 1.0


def test_missing_pages_are_diffed_against_nothing() -> None:
    doc = diff_document("doc", ["same", "only left"], ["same"])
    assert [p.identical for p in doc.pages] == [True, False]
    assert doc.pages[1].similarity == 0.0
    assert 0 < doc.similarity < 1


@pytest.fixture
def run_dir(tmp_path: Path) -> RunDirectory:
    directory = RunDirectory(tmp_path / "run")
    directory.write_output("a", "doc1", ["Ge\u00addächtnis <b>", "page two"])
    directory.write_output("b", "doc1", ["Gedächtnis <b>", "page two"])
    directory.write_output("a", "doc2", ["text"])
    directory.append_result(
        ExtractionResult("doc2", "b", "error", 0.1, error="RuntimeError('boom')")
    )
    directory.write_manifest({"documents": [{"id": "doc1"}, {"id": "doc2"}]})
    return directory


def test_compare_writes_report(run_dir: RunDirectory) -> None:
    path = compare(run_dir.path, "a", "b")
    assert path == run_dir.path / "compare" / "a-vs-b.html"
    html = path.read_text()
    assert 'class="invisible" title="U+00AD SOFT HYPHEN">SHY<' in html
    assert "&lt;b&gt;" in html and "<b>" not in html
    assert "b: RuntimeError(&#x27;boom&#x27;)" in html
    assert html.index('id="doc-doc2"') < html.index('id="doc-doc1"')  # problems first


def test_compare_unknown_extractor(run_dir: RunDirectory) -> None:
    with pytest.raises(ValueError, match=r"no outputs for 'c'.*available: a, b"):
        compare(run_dir.path, "a", "c")


def test_compare_on_real_run(pdf_dir: Path, tmp_path: Path) -> None:
    config = Config(input=pdf_dir, output=tmp_path / "runs", extractors=["pypdfium2", "pypdf"])
    run = Runner(config, name="r").run()
    path = compare(run.path, "pypdfium2", "pypdf", output=tmp_path / "out.html")
    assert path.exists()
    assert path.read_text().count('class="document"') == 5


def test_similarity_matrix(tmp_path: Path) -> None:
    directory = RunDirectory(tmp_path / "run")
    directory.write_output("a", "doc", ["one two three four", "five six"])
    directory.write_output("b", "doc", ["one two\nthree four", "five six"])
    directory.write_output("c", "doc", ["one two", "five seven"])
    directory.write_output("d", "other", ["unrelated"])  # no shared documents with a, b, c

    by_words = similarity_matrix(directory.path, ["a", "b", "c"], Metric.WORDS)
    assert by_words["a", "b"] == by_words["b", "a"] == 1.0
    assert by_words["a", "c"] == 3 / 4  # a has one, two, five of c's one, two, five, seven
    assert by_words["c", "a"] == 3 / 6  # c has one, two, five of a's six words
    assert by_words.agreement("c") < by_words.agreement("a")

    order = similarity_matrix(directory.path, ["a", "b", "c"], Metric.ORDER)
    assert order["a", "c"] == order["c", "a"] == pytest.approx(2 * 3 / 10)
    assert order.ranked_pairs()[0] == ("a", "b", 1.0)

    default = similarity_matrix(directory.path)
    assert default.metric == Metric.NGRAMS
    assert default.extractors == ["a", "b", "c", "d"]
    with pytest.raises(ValueError, match="at least two"):
        similarity_matrix(directory.path, ["a"])


def test_ngrams_reward_intact_sentences_regardless_of_block_order(tmp_path: Path) -> None:
    first, second = "the cat sat on the mat", "a dog ran in the park"
    directory = RunDirectory(tmp_path / "run")
    directory.write_output("reference", "doc", [f"{first}\n{second}"])
    directory.write_output("swapped", "doc", [f"{second}\n{first}"])
    directory.write_output("interleaved", "doc", ["the cat a dog sat ran on in the mat the park"])

    by_words = similarity_matrix(directory.path, metric=Metric.WORDS)
    ngrams = similarity_matrix(directory.path, metric=Metric.NGRAMS)
    order = similarity_matrix(directory.path, metric=Metric.ORDER)

    # All words are there in both cases ...
    assert by_words["swapped", "reference"] == by_words["interleaved", "reference"] == 1.0
    # ... but only swapping whole blocks keeps the sentences intact: just the two 3-word
    # sequences across the block boundary differ.
    assert ngrams["swapped", "reference"] == 8 / 10
    assert ngrams["interleaved", "reference"] == 0.0
    # The order metric penalises the swapped blocks too.
    assert order["swapped", "reference"] < ngrams["swapped", "reference"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            f"# Titel\n**Bundes{SOFT_HYPHEN}wehr**, <u>sagt</u> er.<!-- picture -->|Tabelle|",
            ["Titel", "Bundeswehr", "sagt", "er", "Tabelle"],
        ),
        (f"Lieblings{SOFT_HYPHEN}\nserie", ["Lieblingsserie"]),
        (f"Lieblings{SOFT_HYPHEN} serie", ["Lieblingsserie"]),  # line break replaced by a space
        (f"Lieblings{PDFIUM_HYPHEN}serie", ["Lieblingsserie"]),
        ("Ge-\ndächtnis", ["Gedächtnis"]),
        ("KRIEGS-\nFÜHRUNG", ["KRIEGS", "FÜHRUNG"]),
        ("US-\nPräsident", ["US", "Präsident"]),
        ("Ein- und Ausgang", ["Ein", "und", "Ausgang"]),
    ],
)
def test_words_normalization(text: str, expected: list[str]) -> None:
    assert words(text) == expected


def test_coverage_of_an_empty_output_is_undefined(tmp_path: Path) -> None:
    directory = RunDirectory(tmp_path / "run")
    directory.write_output("full", "doc", ["some words"])
    directory.write_output("empty", "doc", [""])
    matrix = similarity_matrix(directory.path, metric=Metric.WORDS)
    assert matrix["full", "empty"] is None
    assert matrix["empty", "full"] == 0.0
    assert matrix.ranked_pairs() == [("empty", "full", 0.0)]


def test_cli_compare_modes(run_dir: RunDirectory) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["compare", str(run_dir.path)])
    assert result.exit_code == 0, result.output
    assert "too little text" in result.output  # the pages are shorter than 3 words

    result = runner.invoke(app, ["compare", str(run_dir.path), "--metric", "words"])
    assert result.exit_code == 0, result.output
    assert "Inspect a pair with" in result.output

    result = runner.invoke(app, ["compare", str(run_dir.path), "--metric", "order"])
    assert result.exit_code == 0, result.output
    assert "order of blocks" in result.output

    result = runner.invoke(app, ["compare", str(run_dir.path), "a", "b"])
    assert result.exit_code == 0
    assert (run_dir.path / "compare" / "a-vs-b.html").exists()

    result = runner.invoke(app, ["compare", str(run_dir.path), "a"])
    assert result.exit_code == 1
