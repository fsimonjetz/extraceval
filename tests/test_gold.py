from pathlib import Path

import pytest
from typer.testing import CliRunner

from extraceval.cli import app
from extraceval.gold import page_ranges, score, tokens
from extraceval.storage import RunDirectory

ARTICLE = "Die Regierung plant neue Gesetze für den Schutz der Wälder im ganzen Land."
CONTINUED = "Der Minister sagte am Montag, das Vorhaben werde noch dieses Jahr umgesetzt."
OTHER = "Im Sport gewann die Mannschaft am Wochenende überraschend gegen den Meister."


@pytest.fixture
def run_dir(tmp_path: Path) -> RunDirectory:
    """A run of one edition whose article starts on page 2 and continues on page 3."""
    directory = RunDirectory(tmp_path / "run")
    directory.write_manifest(
        {"documents": [{"id": "edition-1234", "source": "/data/Edition_2026_01.pdf"}]}
    )
    good = [OTHER, ARTICLE.upper(), CONTINUED, OTHER]
    jumbled = [OTHER, " ".join(sorted(ARTICLE.split())), CONTINUED, OTHER]
    directory.write_output("good", "edition-1234", good)
    directory.write_output("jumbled", "edition-1234", jumbled)
    return directory


@pytest.fixture
def gold(tmp_path: Path) -> Path:
    root = tmp_path / "gold"
    (root / "Edition_2026_01").mkdir(parents=True)
    (root / "Edition_2026_01" / "2.txt").write_text(f"{ARTICLE}\n\n{CONTINUED}\n")
    return root


def test_article_is_located_across_pages_and_scored(run_dir: RunDirectory, gold: Path) -> None:
    report = score(run_dir.path, gold)
    (result,) = report.articles
    assert result.article.name == "Edition_2026_01/2"
    assert result.pages == [2, 3]
    assert not result.misplaced

    good, jumbled = report.mean("good"), report.mean("jumbled")
    assert good is not None and jumbled is not None
    assert good.words == good.ngrams == 1.0  # case is ignored
    assert jumbled.words == 1.0
    assert jumbled.ngrams < 0.6


def test_pages_repeating_an_article_are_not_located(tmp_path: Path) -> None:
    """Like a front-page teaser whose sentences reappear in the full article further on."""
    directory = RunDirectory(tmp_path / "run")
    directory.write_manifest({"documents": [{"id": "e-1", "source": "/data/E.pdf"}]})
    directory.write_output("tool", "e-1", [f"{ARTICLE} {CONTINUED}", OTHER, f"{OTHER} {ARTICLE}"])
    (tmp_path / "gold" / "E").mkdir(parents=True)
    (tmp_path / "gold" / "E" / "1.txt").write_text(f"{ARTICLE} {CONTINUED}")

    (result,) = score(directory.path, tmp_path / "gold").articles
    assert result.pages == [1]


def test_misplaced_and_missing_articles(run_dir: RunDirectory, gold: Path) -> None:
    (gold / "Edition_2026_01" / "2.txt").rename(gold / "Edition_2026_01" / "10b.txt")
    (gold / "Edition_2026_01" / "e1.txt").write_text("Ganz andere Worte stehen in diesem Text.")
    (gold / "Unknown_Edition").mkdir()

    report = score(run_dir.path, gold)
    misplaced, missing = report.articles
    assert (misplaced.article.page, misplaced.misplaced) == (10, True)
    assert (missing.article.label, missing.article.page, missing.pages) == ("e1", None, [])
    assert report.found == [misplaced]
    assert report.unmatched == ["Unknown_Edition"]


def test_tokens_ignore_case_and_rejoin_hyphenation() -> None:
    assert tokens("WALD-\nschutz im Wald-\nschutz") == ["waldschutz", "im", "waldschutz"]


def test_page_ranges() -> None:
    assert page_ranges([6]) == "6"
    assert page_ranges([12, 10, 11, 15]) == "10-12, 15"


def test_score_command(run_dir: RunDirectory, gold: Path) -> None:
    result = CliRunner().invoke(
        app, ["score", str(run_dir.path), "--gold", str(gold), "--articles"]
    )
    assert result.exit_code == 0, result.output
    assert "1 good" in result.output
    assert "Edition_2026_01" in result.output

    missing = CliRunner().invoke(app, ["score", str(run_dir.path), "--gold", "nope"])
    assert missing.exit_code == 1
