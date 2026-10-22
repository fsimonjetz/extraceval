import json
from pathlib import Path

import pytest

import extraceval
from extraceval import Config, Extractor, ExtractorOptions, Runner, register
from extraceval.storage import RunDirectory


class FakeOptions(ExtractorOptions):
    fail_on: str | None = None


@register("fake")
class Fake(Extractor[FakeOptions]):
    distribution = "pytest"
    calls = 0

    def extract(self, path: Path) -> list[str]:
        type(self).calls += 1
        if self.options.fail_on and self.options.fail_on in path.name:
            raise RuntimeError("boom")
        return [f"{path.stem} page 1", f"{path.stem} page 2"]


@register("fake-broken-setup")
class BrokenSetup(Fake):
    def setup(self) -> None:
        raise RuntimeError("no model")


@register("fake-missing")
class Missing(Fake):
    distribution = "surely-not-installed-xyz"


@pytest.fixture(autouse=True)
def reset_calls() -> None:
    Fake.calls = 0


def make_config(pdf_dir: Path, tmp_path: Path, **kwargs: object) -> Config:
    return Config(input=pdf_dir, output=tmp_path / "runs", **kwargs)  # type: ignore[arg-type]


def test_run_writes_outputs_results_and_manifest(pdf_dir: Path, tmp_path: Path) -> None:
    config = make_config(pdf_dir, tmp_path, sample=3, extractors=["fake", "pypdfium2"])
    result = Runner(config, name="test").run()

    assert result.path == tmp_path / "runs" / "test"
    assert len(result.results) == 6
    assert all(r.status == "ok" and r.pages == 2 for r in result.results)

    run_dir = RunDirectory(result.path)
    doc_id = result.results[0].document
    assert (run_dir.sample_dir / f"{doc_id}.pdf").exists()
    assert run_dir.read_output("fake", doc_id) == [f"{doc_id} page 1", f"{doc_id} page 2"]
    assert len(run_dir.read_results()) == 6

    manifest = json.loads(run_dir.manifest_path.read_text())
    assert set(manifest["extractors"]) == {"fake", "pypdfium2"}
    assert manifest["extractors"]["fake"]["setup_seconds"] is not None
    assert len(manifest["documents"]) == 3


def test_errors_are_recorded_and_do_not_stop_the_run(pdf_dir: Path, tmp_path: Path) -> None:
    config = make_config(
        pdf_dir,
        tmp_path,
        extractors=["fake", "fake-broken-setup"],
        options={"fake": {"fail_on": "deep"}},
    )
    results = Runner(config, name="test").run().results
    by_status = {(r.extractor, r.status) for r in results}
    assert by_status == {("fake", "ok"), ("fake", "error"), ("fake-broken-setup", "error")}
    broken = [r for r in results if r.extractor == "fake-broken-setup"]
    assert len(broken) == 5
    assert all("setup failed" in (r.error or "") for r in broken)


def test_resume_skips_succeeded_pairs_and_retries_errors(pdf_dir: Path, tmp_path: Path) -> None:
    failing = make_config(
        pdf_dir, tmp_path, extractors=["fake"], options={"fake": {"fail_on": "deep"}}
    )
    Runner(failing, name="test").run()
    assert Fake.calls == 5

    Fake.calls = 0
    results = Runner(make_config(pdf_dir, tmp_path, extractors=["fake"]), name="test").run().results
    assert Fake.calls == 1  # only the failed document is retried
    assert all(r.status == "ok" for r in results)
    assert len(RunDirectory(tmp_path / "runs" / "test").read_results()) == 5

    Fake.calls = 0
    Runner(make_config(pdf_dir, tmp_path, extractors=["fake"]), name="test", force=True).run()
    assert Fake.calls == 5


def test_resume_with_other_extractors_keeps_manifest_entries(pdf_dir: Path, tmp_path: Path) -> None:
    Runner(make_config(pdf_dir, tmp_path, extractors=["fake"]), name="test").run()
    Runner(make_config(pdf_dir, tmp_path, extractors=["pypdfium2"]), name="test").run()
    manifest = RunDirectory(tmp_path / "runs" / "test").read_manifest()
    assert set(manifest["extractors"]) == {"fake", "pypdfium2"}
    assert manifest["extractors"]["fake"]["setup_seconds"] is not None


def test_uninstalled_extractors_are_skipped(pdf_dir: Path, tmp_path: Path) -> None:
    runner = Runner(make_config(pdf_dir, tmp_path, extractors=["fake", "fake-missing"]))
    assert [s.name for s in runner.extractors] == ["fake"]
    assert [s.name for s in runner.skipped] == ["fake-missing"]


def test_run_function_with_overrides(pdf_dir: Path, tmp_path: Path) -> None:
    result = extraceval.run(
        pdf_dir, extractors=["fake"], sample=2, output=tmp_path / "out", name="api"
    )
    assert result.path == tmp_path / "out" / "api"
    assert len(result.results) == 2
