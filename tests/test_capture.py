import logging
import sys
from pathlib import Path

import pytest

from extraceval import Config, Extractor, ExtractorOptions, Runner, register

noisy_logger = logging.getLogger("noisy_tool")


@register("fake-noisy")
class Noisy(Extractor[ExtractorOptions]):
    distribution = "pytest"

    def setup(self) -> None:
        # Like libraries that attach their own handler when imported.
        if not noisy_logger.handlers:
            noisy_logger.addHandler(logging.StreamHandler())
            noisy_logger.propagate = False

    def extract(self, path: Path) -> list[str]:
        print(f"printing about {path.name}")
        print("progress 100%", file=sys.stderr)
        noisy_logger.warning("own handler: \x1b[33mcoloured\x1b[0m")
        logging.getLogger("other_tool").warning("via root")
        return ["text"]


@register("fake-silent")
class Silent(Extractor[ExtractorOptions]):
    distribution = "pytest"

    def extract(self, path: Path) -> list[str]:
        return ["text"]


def run(pdf_dir: Path, tmp_path: Path, extractor: str) -> Runner:
    config = Config(input=pdf_dir / "doc 0.pdf", output=tmp_path / "runs", extractors=[extractor])
    return Runner(config, name="r")


def test_tool_output_goes_to_log_not_terminal(
    pdf_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = run(pdf_dir, tmp_path, "fake-noisy").run()

    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert result.tool_log == result.path / "tools.log"
    log = result.tool_log.read_text()
    assert "=== fake-noisy: warm-up ===\nprinting about warmup.pdf" in log
    assert "=== fake-noisy: doc_0-" in log
    assert "progress 100%" in log
    assert "own handler: coloured" in log  # ANSI colour codes stripped
    assert "WARNING other_tool: via root" in log
    assert "fake-noisy: setup" not in log  # silent sections leave no heading


def test_handlers_created_during_a_run_still_work_afterwards(pdf_dir: Path, tmp_path: Path) -> None:
    run(pdf_dir, tmp_path, "fake-noisy").run()
    noisy_logger.warning("after the run")  # must not fail on the closed log file


def test_no_log_when_tools_are_quiet(pdf_dir: Path, tmp_path: Path) -> None:
    assert run(pdf_dir, tmp_path, "fake-silent").run().tool_log is None
