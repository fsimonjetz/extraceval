import json
from collections.abc import Callable
from pathlib import Path

import pytest

from extraceval import extractors
from extraceval.config import Config
from extraceval.extractors import Extractor, ExtractorOptions
from extraceval.runner import Runner
from extraceval.storage import RunDirectory


class FakeOptions(ExtractorOptions):
    fail_on: str | None = None


class Fake(Extractor[FakeOptions]):
    distribution = "pytest"
    calls = 0
    warm_ups = 0

    def extract(self, path: Path) -> list[str]:
        if path.name == "warmup.pdf":
            type(self).warm_ups += 1
        else:
            type(self).calls += 1
        if self.options.fail_on and self.options.fail_on in path.name:
            raise RuntimeError("boom")
        return [f"{path.stem} page 1", f"{path.stem} page 2"]


class BrokenSetup(Fake):
    def setup(self) -> None:
        raise RuntimeError("no model")


class BrokenWarmUp(Fake):
    def warm_up(self) -> None:
        raise RuntimeError("cannot read the warm-up page")


@pytest.fixture(autouse=True)
def fakes(register: Callable[..., None]) -> None:
    register(fake=Fake, **{"fake-broken-setup": BrokenSetup, "fake-broken-warm-up": BrokenWarmUp})
    Fake.calls = Fake.warm_ups = 0


def make_config(pdf_dir: Path, tmp_path: Path, **kwargs: object) -> Config:
    return Config(input=pdf_dir, output=tmp_path / "runs", **kwargs)  # type: ignore[arg-type]


def test_run_writes_outputs_results_and_manifest(pdf_dir: Path, tmp_path: Path) -> None:
    config = make_config(pdf_dir, tmp_path, extractors=["fake", "pypdfium2"])
    result = Runner(config, name="test").run()

    assert result.path == tmp_path / "runs" / "test"
    assert len(result.results) == 10
    assert all(r.status == "ok" and r.pages == 2 for r in result.results)

    run_dir = RunDirectory(result.path)
    doc_id = result.results[0].document
    assert (run_dir.pdf_dir / f"{doc_id}.pdf").exists()
    assert run_dir.read_output("fake", doc_id) == [f"{doc_id} page 1", f"{doc_id} page 2"]
    assert len(run_dir.read_results()) == 10

    manifest = json.loads(run_dir.manifest_path.read_text())
    assert set(manifest["extractors"]) == {"fake", "pypdfium2"}
    assert manifest["extractors"]["fake"]["setup_seconds"] is not None
    assert len(manifest["documents"]) == 5


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


def test_warm_up_runs_once_before_timing(pdf_dir: Path, tmp_path: Path) -> None:
    Runner(make_config(pdf_dir, tmp_path, extractors=["fake"])).run()
    assert (Fake.warm_ups, Fake.calls) == (1, 5)


def test_failed_warm_up_does_not_stop_extraction(pdf_dir: Path, tmp_path: Path) -> None:
    results = Runner(make_config(pdf_dir, tmp_path, extractors=["fake-broken-warm-up"])).run()
    assert all(r.status == "ok" for r in results.results)


def test_builtin_warm_up_reads_bundled_pdf() -> None:
    extractor = extractors.get("pypdfium2")()
    extractor.warm_up()  # raises if the asset is missing from the package
