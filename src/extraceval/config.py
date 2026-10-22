"""Run configuration, from ``extraceval.toml`` or ``[tool.extraceval]`` in ``pyproject.toml``.

Example::

    input = "pdfs"
    sample = 20
    extractors = ["pypdfium2", "pymupdf", "pdfplumber-layout"]  # omit to run all installed

    [options.pymupdf]
    sort = true

    [options.pdfplumber-layout]  # a variant: a new name for a tool with other settings
    tool = "pdfplumber"
    layout = true
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from extraceval import extractors
from extraceval.extractors import Extractor, ExtractorOptions

CONFIG_FILE = "extraceval.toml"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractorSpec:
    """A named, configured instance of a tool, e.g. ``pdfplumber-layout`` -> ``pdfplumber``."""

    name: str
    tool: str
    options: ExtractorOptions

    @property
    def cls(self) -> type[Extractor[Any]]:
        return extractors.get(self.tool)

    def build(self) -> Extractor[Any]:
        return self.cls(self.options)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: Path = Path("pdfs")
    """A PDF file or a directory searched recursively for PDFs."""
    output: Path = Path("runs")
    """Directory in which each run gets its own subdirectory."""
    sample: int | None = Field(default=None, gt=0)
    """Number of documents to draw at random; ``None`` uses all of them."""
    seed: int = 0
    extractors: list[str] | None = None
    """Extractors to run, by name; ``None`` runs every installed tool and every defined variant."""
    options: dict[str, dict[str, Any]] = {}
    """Settings per extractor name. A ``tool`` key makes the entry a variant of that tool."""

    def override(self, **values: Any) -> "Config":
        """A validated copy with the given fields replaced; ``None`` values are ignored."""
        updates = {key: value for key, value in values.items() if value is not None}
        return Config.model_validate(self.model_dump() | updates)

    def resolve_extractors(self) -> list[ExtractorSpec]:
        """Turn names and options into validated specs. Uninstalled tools are included."""
        if self.extractors is not None:
            names = self.extractors
        else:
            installed = [name for name, cls in extractors.registry().items() if cls.is_available()]
            names = list(dict.fromkeys([*installed, *self.options]))
        return [self._spec(name) for name in names]

    def _spec(self, name: str) -> ExtractorSpec:
        settings = dict(self.options.get(name, {}))
        tool = settings.pop("tool", name)
        try:
            cls = extractors.get(tool)
        except LookupError as exc:
            raise ConfigError(str(exc)) from None
        try:
            options = cls.options_model.model_validate(settings)
        except ValidationError as exc:
            raise ConfigError(f"invalid options for extractor {name!r}:\n{exc}") from None
        return ExtractorSpec(name=name, tool=tool, options=options)


def load_config(path: Path | str | None = None) -> Config:
    """Load a config file, or look for one in the working directory and fall back to defaults.

    Relative paths in a config file are resolved against the file's directory.
    """
    if path is None:
        candidates = [Path(CONFIG_FILE), Path("pyproject.toml")]
        path = next((p for p in candidates if _read_table(p) is not None), None)
        if path is None:
            return Config()
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    table = _read_table(path) or {}
    try:
        config = Config.model_validate(table)
    except ValidationError as exc:
        raise ConfigError(f"invalid config in {path}:\n{exc}") from None
    base = path.parent
    return config.model_copy(update={"input": base / config.input, "output": base / config.output})


def _read_table(path: Path) -> dict[str, Any] | None:
    """The extraceval settings in ``path``, or ``None`` if the file does not provide any."""
    if not path.is_file():
        return None
    with path.open("rb") as f:
        data = tomllib.load(f)
    if path.name == "pyproject.toml":
        table: dict[str, Any] | None = data.get("tool", {}).get("extraceval")
        return table
    return data
