import re
from pathlib import Path
from typing import Any, Literal

from extraceval.extractors.base import Extractor, ExtractorOptions

# Marker writes "{page_id}<separator>" before each page; a separator unlikely to occur in text.
_SEPARATOR = "\x00extraceval-page\x00"
_PAGE_MARKER = re.compile(r"\{(\d+)\}" + re.escape(_SEPARATOR))


class MarkerOptions(ExtractorOptions):
    mode: Literal["fast", "balanced"] | None = None
    """``"balanced"`` uses a VLM for layout and full-page OCR; ``None`` picks it on CUDA and
    ``"fast"`` (lightweight layout model, OCR only where the text layer is unusable) otherwise."""
    force_ocr: bool = False
    disable_ocr: bool = False
    keep_pageheader_in_output: bool = False
    keep_pagefooter_in_output: bool = False


class Marker(Extractor[MarkerOptions]):
    """Marker's layout and OCR pipeline (built on Surya), exported as Markdown per page."""

    distribution = "marker-pdf"

    def setup(self) -> None:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict

        config = self.options.model_dump(exclude_none=True) | {
            "paginate_output": True,
            "page_separator": _SEPARATOR,
            "extract_images": False,
            "disable_tqdm": True,
        }
        self._converter: Any = PdfConverter(artifact_dict=create_model_dict(), config=config)

    def extract(self, path: Path) -> list[str]:
        markdown = self._converter(str(path)).markdown
        pages = [""] * self._converter.page_count
        parts = _PAGE_MARKER.split(markdown)
        for page_id, text in zip(parts[1::2], parts[2::2], strict=True):
            pages[int(page_id)] = text.strip()
        return pages
