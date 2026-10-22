from pathlib import Path
from typing import Any, Literal

from extraceval.extractors.base import Extractor, ExtractorOptions


class DoclingOptions(ExtractorOptions):
    format: Literal["markdown", "text"] = "markdown"
    do_ocr: bool = True
    do_table_structure: bool = True


class Docling(Extractor[DoclingOptions]):
    """Docling's layout-model pipeline, exported per page."""

    distribution = "docling"

    def setup(self) -> None:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        pipeline_options = PdfPipelineOptions(**self.options.model_dump(exclude={"format"}))
        self._converter: Any = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        self._converter.initialize_pipeline(InputFormat.PDF)  # load models now, not on first doc

    def extract(self, path: Path) -> list[str]:
        document = self._converter.convert(path).document
        export = (
            document.export_to_markdown
            if self.options.format == "markdown"
            else document.export_to_text
        )
        return [export(page_no=page_no) for page_no in range(1, document.num_pages() + 1)]
