"""ExtracEval: compare PDF-to-text tools on your own documents."""

from extraceval.compare import compare
from extraceval.config import Config, ConfigError, ExtractorSpec, load_config
from extraceval.extractors import Extractor, ExtractorOptions, register
from extraceval.models import Document, ExtractionResult
from extraceval.runner import Runner, RunResult, run

__all__ = [
    "Config",
    "ConfigError",
    "Document",
    "ExtractionResult",
    "Extractor",
    "ExtractorOptions",
    "ExtractorSpec",
    "RunResult",
    "Runner",
    "compare",
    "load_config",
    "register",
    "run",
]
