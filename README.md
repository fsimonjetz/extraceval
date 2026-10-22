# ExtracEval: A PDF-to-Text Evaluation Workbench with a Local VLM Judge

Many types of textual data are only available as PDFs. To use them for NLP and other
applications, they are commonly converted to plain text first. Many tools exist for this, but they
differ considerably in speed and output quality, and good results on standard benchmarks do not
guarantee that a tool handles the idiosyncrasies of *your* specific documents. Comparing tools
usually means setting up and configuring each one, then assessing output quality by either

- manually inspecting the output against the source PDFs, or
- compiling gold-standard data first.

ExtracEval streamlines this process: it runs a sample of your documents through multiple
PDF-to-text tools in a single run, profiles the speed of each, and offers two ways to assess
quality *without gold data*:

1. A side-by-side comparison interface that highlights where the outputs diverge, pointing to
   likely extraction errors, and
2. A judge based on a locally run vision-language model (VLM) that compares each output
   against the rendered page and ranks the tools. No data leaves your machine.

The result is a report of quality and speed per tool, so you can choose the trade-off that fits
your use case.

## Installation

```bash
pip install "extraceval[all]"        # every supported tool
pip install "extraceval[pymupdf,pdfplumber]"   # or pick the tools you need
```

The core install includes `pypdfium2`, so there is always at least one tool to run. Tools that
are not installed are skipped. Note that PyMuPDF is AGPL-licensed.

## Usage

```bash
extraceval list                      # known tools, installed versions, options
extraceval run pdfs/                 # all installed tools on all PDFs in pdfs/
extraceval run pdfs/ -n 20 -e pypdf -e pymupdf --name trial
```

Re-using a run name resumes it: document/tool pairs that already succeeded are skipped (use
`--force` to redo them). The same is available from Python:

```python
import extraceval

result = extraceval.run("pdfs/", sample=20)
```

### Configuration

Without configuration, every installed tool runs with its default settings. To change that, put
an `extraceval.toml` in the working directory (or a `[tool.extraceval]` table in
`pyproject.toml`). Command-line options take precedence.

```toml
input = "pdfs"
output = "runs"
sample = 20
seed = 0
extractors = ["pypdfium2", "pymupdf", "pdfplumber-layout"]  # omit to run all installed

[options.pymupdf]
sort = true

# A variant: the same tool under a new name with different settings.
[options.pdfplumber-layout]
tool = "pdfplumber"
layout = true
```

### Output

Each run gets its own directory:

```
runs/<name>/
  manifest.json                        config, tool versions and options, environment, documents
  sample/<document>.pdf                copies of the sampled PDFs
  outputs/<extractor>/<document>.txt   extracted text, pages separated by form feeds (\f)
  results.jsonl                        status, seconds, pages and characters per document and tool
```

### Comparing outputs

```bash
extraceval compare runs/<name>                   # similarity matrix of all tools
extraceval compare runs/<name> pypdf pymupdf --open
```

Without tool names (or with three or more), `compare` prints how similar each pair of tools'
outputs is, plus each tool's mean similarity to the others. A tool that disagrees with all the
rest stands out at once. Similarity is measured on words, so line breaks and spacing don't count.

With two tool names, it writes a self-contained HTML report to
`runs/<name>/compare/pypdf-vs-pymupdf.html`. It lists the documents ordered by how much the two
tools disagree, followed by a side-by-side diff of each page with changed words highlighted.
Whitespace is normalised before diffing, and invisible characters such as soft hyphens are shown
as markers.

### Adding a tool

Subclass `Extractor` with an options model and register it, either at runtime with
`@extraceval.register("name")` or from any package through an entry point in the
`extraceval.extractors` group:

```python
from pathlib import Path
from extraceval import Extractor, ExtractorOptions


class MyToolOptions(ExtractorOptions):
    fast: bool = False


class MyTool(Extractor[MyToolOptions]):
    distribution = "mytool"  # PyPI name, used for availability and version

    def extract(self, path: Path) -> list[str]:  # one string per page
        import mytool
        return mytool.pages(path, fast=self.options.fast)
```

```toml
[project.entry-points."extraceval.extractors"]
mytool = "mypackage.extractor:MyTool"
```
