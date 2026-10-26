from pathlib import Path

from typer.testing import CliRunner

from extraceval import Config, Extractor, ExtractorOptions, register
from extraceval.cli import app
from extraceval.initialize import initialize


@register("fake-init")
class FakeInit(Extractor[ExtractorOptions]):
    distribution = "pytest"
    seen: list[str] = []  # noqa: RUF012 - records calls across instances

    def extract(self, path: Path) -> list[str]:
        type(self).seen.append(path.name)
        return [] if path.name == "scanned.pdf" else ["text"]


@register("fake-init-broken")
class BrokenInit(FakeInit):
    def setup(self) -> None:
        raise RuntimeError("download failed")


@register("fake-init-missing")
class MissingInit(FakeInit):
    distribution = "surely-not-installed-xyz"


def test_runs_each_extractor_on_both_pages() -> None:
    FakeInit.seen = []
    (result,) = initialize(Config(extractors=["fake-init"]))
    assert result.ok
    assert FakeInit.seen == ["warmup.pdf", "scanned.pdf"]
    assert result.chars == {"text": 4, "scanned": 0}


def test_failures_are_reported_per_extractor() -> None:
    results = initialize(Config(extractors=["fake-init", "fake-init-broken", "fake-init-missing"]))
    ok, broken, missing = results
    assert ok.ok
    assert broken.error is not None and "download failed" in broken.error
    assert missing.error == "surely-not-installed-xyz is not installed"


def test_cli_fails_if_any_extractor_fails() -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["init", "-e", "fake-init"]).exit_code == 0
    result = runner.invoke(app, ["init", "-e", "fake-init", "-e", "fake-init-broken"])
    assert result.exit_code == 1
    assert "fake-init-broken" in result.output
