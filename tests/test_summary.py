from pathlib import Path

import pytest
from typer.testing import CliRunner

from extraceval import summarize
from extraceval.cli import app
from extraceval.models import ExtractionResult
from extraceval.storage import RunDirectory


@pytest.fixture
def run_dir(tmp_path: Path) -> RunDirectory:
    directory = RunDirectory(tmp_path / "run")
    for result in [
        ExtractionResult("d1", "fast", "ok", 0.5, pages=10, chars=100),
        ExtractionResult("d2", "fast", "ok", 1.5, pages=30, chars=300),
        ExtractionResult("d1", "slow", "ok", 4.0, pages=10, chars=90),
        ExtractionResult("d2", "slow", "error", 0.2, error="boom"),
    ]:
        directory.append_result(result)
    directory.write_manifest({"extractors": {"slow": {"setup_seconds": 7.5}}})
    return directory


def test_summarize(run_dir: RunDirectory) -> None:
    fast, slow = summarize(run_dir.path)
    assert (fast.extractor, fast.ok, fast.errors, fast.pages, fast.chars) == ("fast", 2, 0, 40, 400)
    assert fast.seconds == 2.0
    assert fast.pages_per_second == 20.0
    assert fast.seconds_per_document == 1.0
    assert fast.setup_seconds is None

    # errors don't count towards speed
    assert (slow.ok, slow.errors, slow.seconds, slow.pages_per_second) == (1, 1, 4.0, 2.5)
    assert slow.setup_seconds == 7.5


def test_summarize_selected_extractors_in_given_order(run_dir: RunDirectory) -> None:
    assert [s.extractor for s in summarize(run_dir.path, ["slow", "fast"])] == ["slow", "fast"]


def test_summary_command(run_dir: RunDirectory, tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["summary", str(run_dir.path)])
    assert result.exit_code == 0, result.output
    assert "pages/s" in result.output
    assert "7.5" in result.output

    assert CliRunner().invoke(app, ["summary", str(tmp_path / "missing")]).exit_code == 1
