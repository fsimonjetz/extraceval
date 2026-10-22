from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from extraceval.extractors.base import Extractor, ExtractorOptions


class PyMuPDF4LLMOptions(ExtractorOptions):
    format: Literal["markdown", "text"] = "markdown"
    layout: bool = True
    """Use the PyMuPDF Layout model; ``False`` falls back to the older rule-based analysis."""
    header: bool = True
    """Keep page headers (layout mode only)."""
    footer: bool = True
    """Keep page footers (layout mode only)."""
    use_ocr: bool = True
    """OCR pages without a usable text layer (layout mode only)."""
    ocr_language: str = "eng"
    """Tesseract-style language code(s) for OCR, e.g. ``"deu"`` or ``"deu+eng"``."""

    @model_validator(mode="after")
    def _text_needs_layout(self) -> Self:
        if self.format == "text" and not self.layout:
            raise ValueError('format "text" is only available with layout = true')
        return self


class PyMuPDF4LLM(Extractor[PyMuPDF4LLMOptions]):
    """PyMuPDF's LLM-oriented output, with a layout model for reading order and structure."""

    distribution = "pymupdf4llm"

    def extract(self, path: Path) -> list[str]:
        import pymupdf4llm

        # Module-level switch; set on every call since variants may differ.
        pymupdf4llm.use_layout(self.options.layout)
        convert = (
            pymupdf4llm.to_markdown if self.options.format == "markdown" else pymupdf4llm.to_text
        )
        kwargs = {}
        if self.options.layout:
            kwargs = self.options.model_dump(
                include={"header", "footer", "use_ocr", "ocr_language"}
            )
        chunks = convert(str(path), page_chunks=True, show_progress=False, **kwargs)
        return [chunk["text"] for chunk in chunks]
