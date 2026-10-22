from pathlib import Path

from extraceval.extractors.base import Extractor, ExtractorOptions


class Pypdfium2(Extractor[ExtractorOptions]):
    """PDFium's text layer via pypdfium2. A core dependency, so always available."""

    distribution = "pypdfium2"

    def extract(self, path: Path) -> list[str]:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(path)
        try:
            return [page.get_textpage().get_text_range() for page in pdf]
        finally:
            pdf.close()
