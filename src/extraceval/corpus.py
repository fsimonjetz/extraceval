"""Finding and sampling the input PDFs."""

import hashlib
import random
import re
from pathlib import Path

from extraceval.models import Document


def discover(input: Path) -> list[Path]:
    """All PDFs at ``input``: the file itself, or every ``*.pdf`` below a directory, sorted."""
    if input.is_file():
        return [input]
    if not input.is_dir():
        raise FileNotFoundError(f"input not found: {input}")
    return sorted(p for p in input.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")


def sample(paths: list[Path], n: int | None, seed: int = 0) -> list[Path]:
    """Draw ``n`` paths reproducibly for a given seed; all of them if ``n`` is ``None``."""
    if n is None or n >= len(paths):
        return list(paths)
    return sorted(random.Random(seed).sample(paths, n))


def document_id(path: Path) -> str:
    stem = re.sub(r"[^\w.-]+", "_", path.stem).strip("_") or "document"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    return f"{stem}-{digest}"


def load(input: Path, n: int | None = None, seed: int = 0) -> list[Document]:
    paths = discover(input)
    if not paths:
        raise FileNotFoundError(f"no PDFs found in {input}")
    return [Document(id=document_id(p), path=p) for p in sample(paths, n, seed)]
