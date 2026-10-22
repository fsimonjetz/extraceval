from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Document:
    id: str
    """Stable identifier: sanitised file stem plus a short content hash."""
    path: Path


@dataclass(frozen=True)
class ExtractionResult:
    """Outcome of running one extractor on one document."""

    document: str
    extractor: str
    status: Literal["ok", "error"]
    seconds: float
    pages: int = 0
    chars: int = 0
    error: str | None = None
