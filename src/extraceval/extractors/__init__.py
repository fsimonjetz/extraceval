"""The built-in extractors by name."""

from typing import Any

from extraceval.extractors.base import Extractor, ExtractorOptions
from extraceval.extractors.docling import Docling
from extraceval.extractors.pdfminer import Pdfminer
from extraceval.extractors.pdfplumber import Pdfplumber
from extraceval.extractors.pymupdf import PyMuPDF
from extraceval.extractors.pymupdf4llm import PyMuPDF4LLM
from extraceval.extractors.pypdf import Pypdf
from extraceval.extractors.pypdfium2 import Pypdfium2

__all__ = ["EXTRACTORS", "Extractor", "ExtractorOptions", "UnknownExtractorError", "get"]

EXTRACTORS: dict[str, type[Extractor[Any]]] = {
    "docling": Docling,
    "pdfminer": Pdfminer,
    "pdfplumber": Pdfplumber,
    "pymupdf": PyMuPDF,
    "pymupdf4llm": PyMuPDF4LLM,
    "pypdf": Pypdf,
    "pypdfium2": Pypdfium2,
}


class UnknownExtractorError(LookupError):
    def __init__(self, name: str) -> None:
        super().__init__(f"unknown extractor {name!r} (known: {', '.join(EXTRACTORS)})")


def get(name: str) -> type[Extractor[Any]]:
    try:
        return EXTRACTORS[name]
    except KeyError:
        raise UnknownExtractorError(name) from None
