from pathlib import Path

import pytest

from extraceval import extractors
from extraceval.extractors.pdfplumber import Pdfplumber, PdfplumberOptions


def test_unknown_extractor() -> None:
    with pytest.raises(extractors.UnknownExtractorError, match="nope"):
        extractors.get("nope")


def test_options_model_is_taken_from_type_parameter() -> None:
    assert Pdfplumber.options_model is PdfplumberOptions
    assert Pdfplumber().options == PdfplumberOptions()


@pytest.mark.parametrize("name", list(extractors.EXTRACTORS))
def test_builtin_extracts_pages(name: str, pdf_dir: Path) -> None:
    extractor = extractors.get(name)()
    extractor.setup()
    pages = extractor.extract(pdf_dir / "doc 1.pdf")
    assert len(pages) == 2
    assert "Document 1" in pages[0]
    assert "page two" in pages[1]
