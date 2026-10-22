from pathlib import Path

import pytest

from extraceval import Extractor, ExtractorOptions, extractors, register
from extraceval.extractors.pdfplumber import Pdfplumber, PdfplumberOptions


def test_builtins_are_discovered_via_entry_points() -> None:
    names = extractors.registry()
    builtins = {"pypdfium2", "pypdf", "pymupdf", "pymupdf4llm", "pdfplumber", "pdfminer", "docling"}
    assert builtins <= set(names)
    assert names["pdfplumber"] is Pdfplumber


def test_unknown_extractor() -> None:
    with pytest.raises(extractors.UnknownExtractorError, match="nope"):
        extractors.get("nope")


def test_options_model_is_taken_from_type_parameter() -> None:
    assert Pdfplumber.options_model is PdfplumberOptions
    assert Pdfplumber().options == PdfplumberOptions()


def test_register_runtime_extractor() -> None:
    @register("test-upper")
    class Upper(Extractor[ExtractorOptions]):
        distribution = "pytest"

        def extract(self, path: Path) -> list[str]:
            return [path.name.upper()]

    assert extractors.get("test-upper") is Upper
    assert Upper.is_available()


def test_missing_distribution_is_unavailable() -> None:
    class Missing(Extractor[ExtractorOptions]):
        distribution = "surely-not-installed-xyz"

        def extract(self, path: Path) -> list[str]:
            return []

    assert Missing.version() is None
    assert not Missing.is_available()


@pytest.mark.parametrize(
    "name", ["pypdfium2", "pypdf", "pymupdf", "pymupdf4llm", "pdfplumber", "pdfminer", "docling"]
)
def test_builtin_extracts_pages(name: str, pdf_dir: Path) -> None:
    cls = extractors.get(name)
    if not cls.is_available():
        pytest.skip(f"{cls.distribution} not installed")
    extractor = cls()
    extractor.setup()
    pages = extractor.extract(pdf_dir / "doc 1.pdf")
    assert len(pages) == 2
    assert "Document 1" in pages[0]
    assert "page two" in pages[1]
