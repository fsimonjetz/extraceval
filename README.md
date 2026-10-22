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
