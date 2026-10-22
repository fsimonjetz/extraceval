from pathlib import Path

import pytest

from extraceval import corpus


def test_discover_is_recursive_and_case_insensitive(pdf_dir: Path) -> None:
    paths = corpus.discover(pdf_dir)
    assert len(paths) == 5
    assert pdf_dir / "nested" / "deep.PDF" in paths


def test_discover_single_file(pdf_dir: Path) -> None:
    path = pdf_dir / "doc 0.pdf"
    assert corpus.discover(path) == [path]


def test_discover_missing_input(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        corpus.discover(tmp_path / "missing")


def test_sample_is_reproducible(pdf_dir: Path) -> None:
    paths = corpus.discover(pdf_dir)
    assert corpus.sample(paths, 3, seed=1) == corpus.sample(paths, 3, seed=1)
    assert len(corpus.sample(paths, 3, seed=1)) == 3
    assert corpus.sample(paths, None) == paths
    assert corpus.sample(paths, 100) == paths


def test_document_id_is_sanitised_and_content_based(pdf_dir: Path, tmp_path: Path) -> None:
    doc_id = corpus.document_id(pdf_dir / "doc 0.pdf")
    assert doc_id.startswith("doc_0-")
    copy = tmp_path / "doc 0.pdf"
    copy.write_bytes((pdf_dir / "doc 0.pdf").read_bytes())
    assert corpus.document_id(copy) == doc_id
