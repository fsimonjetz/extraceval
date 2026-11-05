"""Finding the input PDFs."""

import hashlib
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


def document_id(path: Path) -> str:
    stem = re.sub(r"[^\w.-]+", "_", path.stem).strip("_") or "document"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    return f"{stem}-{digest}"


def load(input: Path) -> list[Document]:
    paths = discover(input)
    if not paths:
        raise FileNotFoundError(f"no PDFs found in {input}")
    return [Document(id=document_id(p), path=p) for p in paths]
