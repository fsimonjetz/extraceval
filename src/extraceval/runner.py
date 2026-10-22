"""Runs every configured extractor over the sampled documents and stores the outputs."""

import logging
import platform
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

from extraceval import corpus
from extraceval.capture import capture
from extraceval.config import Config, ExtractorSpec, load_config
from extraceval.extractors import Extractor
from extraceval.models import Document, ExtractionResult
from extraceval.storage import RunDirectory

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    path: Path
    results: list[ExtractionResult]
    tool_log: Path | None = None
    """Messages the tools printed or logged during the run, if any."""


class Runner:
    """Prepares a run (sample, extractors, run directory) on creation; ``run`` executes it.

    Re-using a run name resumes it: pairs that already succeeded are skipped unless ``force``.
    """

    def __init__(self, config: Config, name: str | None = None, force: bool = False) -> None:
        self.config = config
        self.force = force
        self.created = datetime.now().astimezone()
        self.name = name or self.created.strftime("%Y%m%d-%H%M%S")
        self.directory = RunDirectory(config.output / self.name)
        self.documents = corpus.load(config.input, config.sample, config.seed)

        specs = config.resolve_extractors()
        self.extractors = [spec for spec in specs if spec.cls.is_available()]
        self.skipped = [spec for spec in specs if spec not in self.extractors]
        for spec in self.skipped:
            log.warning("skipping %r: %s is not installed", spec.name, spec.cls.distribution)

    @property
    def total(self) -> int:
        return len(self.documents) * len(self.extractors)

    def run(self, on_result: Callable[[ExtractionResult], None] | None = None) -> RunResult:
        documents = [self.directory.add_document(doc) for doc in self.documents]
        previous = {(r.document, r.extractor): r for r in self.directory.read_results()}
        earlier = self.directory.read_manifest().get("extractors", {})
        setup_seconds: dict[str, float] = {}
        self.directory.write_manifest(self._manifest(setup_seconds, earlier))

        with capture(self.directory.log_path) as tool_log:
            for spec in self.extractors:
                todo: list[Document] = []
                for doc in documents:
                    done = previous.get((doc.id, spec.name))
                    if done and done.status == "ok" and not self.force:
                        if on_result:
                            on_result(done)
                    else:
                        todo.append(doc)
                if not todo:
                    continue

                extractor = spec.build()
                start = time.perf_counter()
                try:
                    with tool_log.section(f"{spec.name}: setup"):
                        extractor.setup()
                except Exception as exc:
                    log.exception("setup of %r failed", spec.name)
                    for doc in todo:
                        error = _error(doc, spec, 0.0, f"setup failed: {exc!r}")
                        self._record(error, previous, on_result)
                    continue
                try:
                    with tool_log.section(f"{spec.name}: warm-up"):
                        extractor.warm_up()
                except Exception:
                    log.warning("warm-up of %r failed; continuing without it", spec.name)
                setup_seconds[spec.name] = time.perf_counter() - start

                for doc in todo:
                    with tool_log.section(f"{spec.name}: {doc.id}"):
                        result = self._extract(extractor, spec, doc)
                    self._record(result, previous, on_result)

        self.directory.write_manifest(self._manifest(setup_seconds, earlier))
        results = [
            previous[doc.id, spec.name]
            for spec in self.extractors
            for doc in documents
            if (doc.id, spec.name) in previous
        ]
        self.directory.write_results(list(previous.values()))
        return RunResult(
            path=self.directory.path,
            results=results,
            tool_log=None if tool_log.empty else tool_log.path,
        )

    def _extract(
        self, extractor: Extractor[Any], spec: ExtractorSpec, doc: Document
    ) -> ExtractionResult:
        """Run one extraction. The single place to add isolation (subprocess, timeout) later."""
        start = time.perf_counter()
        try:
            pages = extractor.extract(doc.path)
        except Exception as exc:
            return _error(doc, spec, time.perf_counter() - start, repr(exc))
        seconds = time.perf_counter() - start
        self.directory.write_output(spec.name, doc.id, pages)
        return ExtractionResult(
            document=doc.id,
            extractor=spec.name,
            status="ok",
            seconds=seconds,
            pages=len(pages),
            chars=sum(map(len, pages)),
        )

    def _record(
        self,
        result: ExtractionResult,
        results: dict[tuple[str, str], ExtractionResult],
        on_result: Callable[[ExtractionResult], None] | None,
    ) -> None:
        results[result.document, result.extractor] = result
        self.directory.append_result(result)
        if on_result:
            on_result(result)

    def _manifest(
        self, setup_seconds: dict[str, float], earlier: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Describe the run. Extractors from earlier sessions of a resumed run are kept."""
        current = {
            spec.name: {
                "tool": spec.tool,
                "version": spec.cls.version(),
                "options": spec.options.model_dump(mode="json"),
                "setup_seconds": setup_seconds.get(
                    spec.name, earlier.get(spec.name, {}).get("setup_seconds")
                ),
            }
            for spec in self.extractors
        }
        return {
            "name": self.name,
            "created": self.created.isoformat(timespec="seconds"),
            "extraceval": version("extraceval"),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "config": self.config.model_dump(mode="json"),
            "extractors": earlier | current,
            "skipped": [spec.name for spec in self.skipped],
            "documents": [{"id": d.id, "source": str(d.path)} for d in self.documents],
        }


def run(
    input: Path | str | None = None,
    *,
    config: Config | Path | str | None = None,
    sample: int | None = None,
    seed: int | None = None,
    extractors: list[str] | None = None,
    output: Path | str | None = None,
    name: str | None = None,
    force: bool = False,
) -> RunResult:
    """Run the extractors over a sample of PDFs and save their outputs.

    ``config`` is a ``Config``, a path to a config file, or ``None`` to use ``extraceval.toml`` /
    ``pyproject.toml`` in the working directory if present. Keyword arguments override it.
    """
    if not isinstance(config, Config):
        config = load_config(config)
    config = config.override(
        input=input, sample=sample, seed=seed, extractors=extractors, output=output
    )
    return Runner(config, name=name, force=force).run()


def _error(doc: Document, spec: ExtractorSpec, seconds: float, message: str) -> ExtractionResult:
    return ExtractionResult(
        document=doc.id, extractor=spec.name, status="error", seconds=seconds, error=message
    )
