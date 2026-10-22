from pathlib import Path

from extraceval.extractors.base import Extractor, ExtractorOptions


class PdfminerOptions(ExtractorOptions):
    """Layout analysis parameters, passed to ``pdfminer.layout.LAParams``."""

    line_overlap: float = 0.5
    char_margin: float = 2.0
    line_margin: float = 0.5
    word_margin: float = 0.1
    boxes_flow: float | None = 0.5
    detect_vertical: bool = False
    all_texts: bool = False


class Pdfminer(Extractor[PdfminerOptions]):
    distribution = "pdfminer.six"

    def extract(self, path: Path) -> list[str]:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LAParams, LTTextContainer

        laparams = LAParams(**self.options.model_dump())
        return [
            "".join(element.get_text() for element in page if isinstance(element, LTTextContainer))
            for page in extract_pages(path, laparams=laparams)
        ]
