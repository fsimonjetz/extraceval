from collections.abc import Iterator
from pathlib import Path
from typing import Any

from extraceval.extractors.base import Extractor, ExtractorOptions


class PdfminerOptions(ExtractorOptions):
    """Layout analysis parameters, passed to ``pdfminer.layout.LAParams``.

    ``all_texts`` is on by default because some newspapers put all text inside figures (form
    XObjects), which pdfminer would otherwise not split into lines and words.
    """

    line_overlap: float = 0.5
    char_margin: float = 2.0
    line_margin: float = 0.5
    word_margin: float = 0.1
    boxes_flow: float | None = 0.5
    detect_vertical: bool = False
    all_texts: bool = True


class Pdfminer(Extractor[PdfminerOptions]):
    distribution = "pdfminer.six"

    def extract(self, path: Path) -> list[str]:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LAParams

        laparams = LAParams(**self.options.model_dump())
        return ["".join(_texts(page)) for page in extract_pages(path, laparams=laparams)]


def _texts(element: Any) -> Iterator[str]:
    """Text of all text boxes, including those nested in figures."""
    from pdfminer.layout import LTContainer, LTTextContainer

    if isinstance(element, LTTextContainer):
        yield element.get_text()
    elif isinstance(element, LTContainer):
        for child in element:
            yield from _texts(child)
