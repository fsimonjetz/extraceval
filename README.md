# ExtracEval: Choosing a PDF-to-Text Tool for Newspaper Editions

ExtracEval runs whole newspaper editions (PDFs) through several PDF-to-text tools in a single run,
profiles the speed of each, and measures quality in two ways: against gold texts of individual
articles (e.g. copied from a press database), and by where the tools' outputs diverge, as a
matrix of how much they agree and as a side-by-side diff of two tools. The result shows quality
and speed per tool, to choose the trade-off that fits the corpus.

It is meant to be installed and prepared on a machine with internet access and then used
without it (see [Offline use](#offline-use)).

## Installation

```bash
pip install extraceval
```

This installs pypdfium2, pypdf, PyMuPDF, pymupdf4llm, pdfplumber, pdfminer.six and Docling.
Docling pulls in PyTorch and downloads its models on first use. Note that PyMuPDF and pymupdf4llm
are AGPL-licensed.

### Offline use

Several tools download models the first time they run. To get these downloads out of the way,
e.g. before moving to a machine without internet access, run

```bash
extraceval init
```

This runs each installed tool, with the options from your configuration, on a bundled page with a
text layer and on a scanned page, which makes the tools load their OCR models too. It shows how
much text each tool got from each page (none from the scanned page means the tool does no OCR)
and fails if any tool does. Afterwards, set `HF_HUB_OFFLINE=1` so that a missing model fails
straight away instead of after a network timeout.

## Usage

```bash
extraceval list                      # known tools, installed versions, options
extraceval run pdfs/                 # all tools on all PDFs in pdfs/
extraceval run pdfs/ -e pypdf -e pymupdf --name trial
```

After a run, a table shows each tool's success rate and speed in pages per second;
`extraceval summary runs/<name>` shows it again later. Speed only counts the extraction itself:
one-off costs such as imports and model loading are measured separately as setup time, which
includes extracting a tiny bundled warm-up page with each tool.

Re-using a run name resumes it: document/tool pairs that already succeeded are skipped (use
`--force` to redo them).

### Configuration

Without configuration, every tool runs with its default settings. To change that, put
an `extraceval.toml` in the working directory (or a `[tool.extraceval]` table in
`pyproject.toml`). Command-line options take precedence.

```toml
input = "pdfs"
output = "runs"
gold = "gold"
extractors = ["pypdfium2", "pymupdf", "pdfplumber-layout"]  # omit to run all

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
  pdfs/<document>.pdf                  copies of the input PDFs
  outputs/<extractor>/<document>.txt   extracted text, pages separated by form feeds (\f)
  results.jsonl                        status, seconds, pages and characters per document and tool
  tools.log                            warnings and other output from the tools, by tool and document
```

### Scoring against gold texts

Gold texts are clean versions of individual articles, one plain-text file per article, in a
folder named after the PDF they appear in, with the page the article starts on as the file name:

```
gold/
  SPIEGEL_2026_37/        for SPIEGEL_2026_37.pdf
    6.txt
    13.txt
```

```bash
extraceval score runs/<name>              # all tools in the run
extraceval score runs/<name> --articles   # also show the scores per article
```

`score` shows, per tool, the mean share of each gold article it recovers, next to its speed:

| Column | Share of the article's | Answers |
| --- | --- | --- |
| 3-word seq. | 3-word sequences that the tool also has | Are sentences intact? |
| words | words that the tool also has, in any order | Is the text there at all? |

As the gold covers only some articles of an edition, only this recall is measured: text a tool
adds, such as headers, does not count against it. Words are compared as in `compare` below,
and also ignoring case. Each article counts equally, regardless of its length.

Each article is looked for on all pages, as articles are often continued on later pages and the
start page may not be exact (e.g. when an article opens with a full-page photo). It is located
on the pages on which the tools' outputs contain, on average, at least 5% of its 3-word
sequences, and every tool is scored on these same pages. `score` notes articles found on other
pages than the file name says, and articles that are not found at all and therefore not scored.

The gold directory defaults to `gold` in the working directory; change it with `gold` in the
configuration or `--gold`.

### Comparing outputs

```bash
extraceval compare runs/<name>                   # agreement matrix of all tools
extraceval compare runs/<name> pypdf pymupdf --open
```

Without tool names (or with three or more), `compare` prints a matrix of how much each tool's
output agrees with the others', next to each tool's speed in pages per second. `--metric`
chooses what is compared:

| Metric | Each cell shows | Answers |
| --- | --- | --- |
| `ngrams` (default) | share of the column tool's 3-word sequences the row tool also has | Are sentences intact? |
| `words` | share of the column tool's words the row tool also has, in any order | Is the text there at all? |
| `order` | similarity of the whole word sequences (symmetric) | Do the tools agree on the order of blocks? |

So you can read off, for example, that a fast tool contains 90% of a slow tool's 3-word
sequences. `ngrams` barely changes when two tools put whole articles in a different order, but
drops sharply when a tool mixes up text, e.g. by reading across columns.

All metrics compare words only: markup, punctuation and line breaks are ignored, and words
hyphenated at a line break are joined again, so tools that rejoin lines into paragraphs are not
penalised for it.

With two tool names, it writes a self-contained HTML report to
`runs/<name>/compare/pypdf-vs-pymupdf.html`. It lists the documents ordered by how much the two
tools disagree, followed by a side-by-side diff of each page with changed words highlighted.
Whitespace is normalised before diffing, and invisible characters such as soft hyphens are shown
as markers.

### Adding a tool

Add a module to `src/extraceval/extractors/` with a subclass of `Extractor` that returns one
string per page, add it to `EXTRACTORS` in `extractors/__init__.py`, and add the tool to the
dependencies in `pyproject.toml`.
