from pathlib import Path

from extraceval.extractors.base import Extractor, ExtractorOptions


class PyMuPDFOptions(ExtractorOptions):
    sort: bool = False
    """Reorder text blocks top-left to bottom-right instead of using the content stream order."""


class PyMuPDF(Extractor[PyMuPDFOptions]):
    distribution = "pymupdf"

    def extract(self, path: Path) -> list[str]:
        import pymupdf

        with pymupdf.open(path) as doc:
            return [page.get_text(sort=self.options.sort) for page in doc]
