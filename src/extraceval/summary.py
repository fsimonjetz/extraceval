"""Speed and success per extractor, aggregated from a run's stored results."""

from dataclasses import dataclass
from pathlib import Path

from extraceval.storage import RunDirectory


@dataclass(frozen=True)
class ExtractorSummary:
    extractor: str
    ok: int
    errors: int
    pages: int
    chars: int
    seconds: float
    """Total extraction time over successful documents, excluding setup."""
    setup_seconds: float | None
    """One-time setup and warm-up time, if recorded."""

    @property
    def seconds_per_document(self) -> float | None:
        return self.seconds / self.ok if self.ok else None

    @property
    def pages_per_second(self) -> float | None:
        return self.pages / self.seconds if self.seconds else None


def summarize(run: Path | str, extractors: list[str] | None = None) -> list[ExtractorSummary]:
    """One summary per extractor in the run, or per name in ``extractors``, in that order."""
    directory = RunDirectory(Path(run))
    results = directory.read_results()
    setup = directory.read_manifest().get("extractors", {})
    names = extractors or list(dict.fromkeys(r.extractor for r in results))

    summaries = []
    for name in names:
        rows = [r for r in results if r.extractor == name]
        ok = [r for r in rows if r.status == "ok"]
        summaries.append(
            ExtractorSummary(
                extractor=name,
                ok=len(ok),
                errors=len(rows) - len(ok),
                pages=sum(r.pages for r in ok),
                chars=sum(r.chars for r in ok),
                seconds=sum(r.seconds for r in ok),
                setup_seconds=setup.get(name, {}).get("setup_seconds"),
            )
        )
    return summaries
