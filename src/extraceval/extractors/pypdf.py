from pathlib import Path
from typing import Literal

from extraceval.extractors.base import Extractor, ExtractorOptions


class PypdfOptions(ExtractorOptions):
    extraction_mode: Literal["plain", "layout"] = "plain"


class Pypdf(Extractor[PypdfOptions]):
    distribution = "pypdf"

    def extract(self, path: Path) -> list[str]:
        from pypdf import PdfReader

        reader = PdfReader(path)
        return [
            page.extract_text(extraction_mode=self.options.extraction_mode) for page in reader.pages
        ]
