from pathlib import Path

from extraceval.extractors.base import Extractor, ExtractorOptions


class PdfplumberOptions(ExtractorOptions):
    layout: bool = False
    x_tolerance: float = 3
    y_tolerance: float = 3


class Pdfplumber(Extractor[PdfplumberOptions]):
    distribution = "pdfplumber"

    def extract(self, path: Path) -> list[str]:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            return [page.extract_text(**self.options.model_dump()) or "" for page in pdf.pages]
