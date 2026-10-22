"""Side-by-side comparison of extractor outputs."""

from extraceval.compare.diff import DocumentDiff, PageDiff, diff_document
from extraceval.compare.matrix import SimilarityMatrix, similarity_matrix
from extraceval.compare.report import compare

__all__ = [
    "DocumentDiff",
    "PageDiff",
    "SimilarityMatrix",
    "compare",
    "diff_document",
    "similarity_matrix",
]
