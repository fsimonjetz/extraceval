from pathlib import Path

import pytest
from fpdf import FPDF


def make_pdf(path: Path, pages: list[str]) -> Path:
    pdf = FPDF()
    pdf.set_font("helvetica", size=12)
    for text in pages:
        pdf.add_page()
        pdf.multi_cell(0, 10, text)
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return path


@pytest.fixture
def pdf_dir(tmp_path: Path) -> Path:
    """Five two-page PDFs, one of them in a subdirectory."""
    root = tmp_path / "pdfs"
    for i in range(4):
        make_pdf(root / f"doc {i}.pdf", [f"Document {i}, page one.", f"Document {i}, page two."])
    make_pdf(root / "nested" / "deep.PDF", ["Nested page one.", "Nested page two."])
    return root
