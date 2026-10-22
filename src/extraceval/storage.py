"""On-disk layout of a run, read by later stages (comparison, judging, reporting)::

<run>/
  manifest.json                    resolved config, tool versions, environment, documents
  sample/<document>.pdf            copies of the sampled inputs
  outputs/<extractor>/<document>.txt   extracted text, pages separated by form feeds
  results.jsonl                    one ExtractionResult per (document, extractor)
  tools.log                        what the tools printed or logged, by tool and document
"""

import json
import shutil
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from extraceval.models import Document, ExtractionResult

PAGE_SEPARATOR = "\f"


class RunDirectory:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.manifest_path = path / "manifest.json"
        self.results_path = path / "results.jsonl"
        self.log_path = path / "tools.log"
        self.sample_dir = path / "sample"
        self.outputs_dir = path / "outputs"

    def add_document(self, document: Document) -> Document:
        """Copy a document into the run and return it pointing at the copy."""
        self.sample_dir.mkdir(parents=True, exist_ok=True)
        target = self.sample_dir / f"{document.id}.pdf"
        if not target.exists():
            shutil.copy2(document.path, target)
        return Document(id=document.id, path=target)

    def extractors(self) -> list[str]:
        """Names of the extractors with outputs in this run."""
        if not self.outputs_dir.is_dir():
            return []
        return sorted(p.name for p in self.outputs_dir.iterdir() if p.is_dir())

    def require_extractors(self, names: Iterable[str]) -> None:
        available = self.extractors()
        for name in names:
            if name not in available:
                known = ", ".join(available) or "none"
                raise ValueError(f"no outputs for {name!r} in {self.path} (available: {known})")

    def documents(self) -> list[str]:
        """Document ids in manifest order, falling back to whatever outputs exist."""
        manifest = self.read_manifest()
        if "documents" in manifest:
            return [doc["id"] for doc in manifest["documents"]]
        return sorted({p.stem for p in self.outputs_dir.glob("*/*.txt")})

    def output_path(self, extractor: str, document: str) -> Path:
        return self.outputs_dir / extractor / f"{document}.txt"

    def write_output(self, extractor: str, document: str, pages: list[str]) -> None:
        path = self.output_path(extractor, document)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(PAGE_SEPARATOR.join(pages), encoding="utf-8")

    def read_output(self, extractor: str, document: str) -> list[str]:
        text = self.output_path(extractor, document).read_text(encoding="utf-8")
        return text.split(PAGE_SEPARATOR)

    def read_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {}
        manifest: dict[str, Any] = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return manifest

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def append_result(self, result: ExtractionResult) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        with self.results_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(result)) + "\n")

    def read_results(self) -> list[ExtractionResult]:
        """Stored results, keeping only the latest per (document, extractor)."""
        if not self.results_path.exists():
            return []
        latest: dict[tuple[str, str], ExtractionResult] = {}
        with self.results_path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    result = ExtractionResult(**json.loads(line))
                    latest[result.document, result.extractor] = result
        return list(latest.values())

    def write_results(self, results: list[ExtractionResult]) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        lines = (json.dumps(asdict(r)) + "\n" for r in results)
        self.results_path.write_text("".join(lines), encoding="utf-8")
