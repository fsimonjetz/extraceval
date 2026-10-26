"""Prepare tools for offline use.

Many tools download models or other files the first time they run. Running each one on a page
with a text layer and on a scanned page (which triggers OCR) gets these downloads out of the way,
e.g. while building a container image for a machine without internet access.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.resources import as_file, files

from extraceval.config import Config, ExtractorSpec

PAGES = {"text": "warmup.pdf", "scanned": "scanned.pdf"}
"""Bundled test pages by kind."""


@dataclass
class InitResult:
    extractor: str
    seconds: float = 0.0
    chars: dict[str, int] = field(default_factory=dict)
    """Characters extracted per kind of page; 0 on the scanned page means no OCR."""
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def initialize(
    config: Config, on_start: Callable[[ExtractorSpec], None] | None = None
) -> list[InitResult]:
    """Set up each configured extractor and run it on the bundled test pages.

    Unlike a run, tool output is not captured, so download progress stays visible.
    """
    results = []
    for spec in config.resolve_extractors():
        if on_start:
            on_start(spec)
        result = InitResult(spec.name)
        results.append(result)
        if not spec.cls.is_available():
            result.error = f"{spec.cls.distribution} is not installed"
            continue
        start = time.perf_counter()
        try:
            extractor = spec.build()
            extractor.setup()
            for kind, name in PAGES.items():
                with as_file(files("extraceval") / "assets" / name) as path:
                    result.chars[kind] = sum(map(len, extractor.extract(path)))
        except Exception as exc:
            result.error = repr(exc)
        result.seconds = time.perf_counter() - start
    return results
