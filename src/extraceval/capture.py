"""Keep the extraction tools' own output (prints, warnings, progress bars, logging) out of the
terminal and in a log file in the run directory instead.

Tools are imported lazily inside ``setup``/``extract``, so logging handlers they create there bind
to the redirected stream. That stream is a forwarding ``_Sink`` rather than the file itself, so the
handlers keep working, writing to the real stderr again, after the run has closed its log.
"""

import io
import logging
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import TextIO

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class _Sink(io.TextIOBase):
    def __init__(self) -> None:
        self.target: TextIO | None = None
        self.heading: str | None = None
        """Written before the next output, so that silent sections leave no trace."""

    def _stream(self) -> TextIO:
        return self.target or sys.__stderr__ or io.StringIO()

    def write(self, text: str) -> int:
        if self.target is None:
            return self._stream().write(text)
        if self.heading and text:
            self.target.write(f"\n=== {self.heading} ===\n")
            self.heading = None
        return self.target.write(ANSI_ESCAPE.sub("", text))

    def flush(self) -> None:
        self._stream().flush()

    def isatty(self) -> bool:
        return False


_sink = _Sink()


class ToolLog:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def section(self, title: str) -> Iterator[None]:
        """Send everything written during the block to the log, under a heading."""
        _sink.heading = title
        try:
            with redirect_stdout(_sink), redirect_stderr(_sink):
                yield
        finally:
            _sink.heading = None
            _sink.flush()

    @property
    def empty(self) -> bool:
        return not self.path.exists() or self.path.stat().st_size == 0


@contextmanager
def capture(path: Path) -> Iterator[ToolLog]:
    """Append tool output and all log records of level WARNING and up to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        _sink.target = file
        handler = logging.StreamHandler(_sink)
        handler.setLevel(logging.WARNING)
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        try:
            yield ToolLog(path)
        finally:
            logging.getLogger().removeHandler(handler)
            _sink.flush()
            _sink.target = None
