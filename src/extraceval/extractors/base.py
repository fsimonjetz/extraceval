"""The interface every PDF-to-text tool implements."""

from abc import ABC, abstractmethod
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any, ClassVar, cast, get_args, get_origin

from pydantic import BaseModel, ConfigDict


class ExtractorOptions(BaseModel):
    """Base class for an extractor's settings. Unknown keys are rejected so typos fail loudly."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Extractor[O: ExtractorOptions](ABC):
    """A PDF-to-text tool.

    Subclasses set ``distribution`` and implement ``extract``. The options model is taken from
    the type parameter, so ``class Foo(Extractor[FooOptions])`` is all it takes. Import the
    underlying library inside ``setup``/``extract`` so this module imports without it installed.
    """

    distribution: ClassVar[str]
    """Name of the PyPI distribution providing the tool, used for availability and versioning."""

    options_model: ClassVar[type[ExtractorOptions]] = ExtractorOptions

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for base in getattr(cls, "__orig_bases__", ()):
            if get_origin(base) is Extractor:
                (param,) = get_args(base)
                if isinstance(param, type) and issubclass(param, ExtractorOptions):
                    cls.options_model = param

    def __init__(self, options: O | None = None) -> None:
        self.options: O = options if options is not None else cast(O, self.options_model())

    @classmethod
    def version(cls) -> str | None:
        """Installed version of the underlying tool, or ``None`` if it is not installed."""
        try:
            return version(cls.distribution)
        except PackageNotFoundError:
            return None

    @classmethod
    def is_available(cls) -> bool:
        return cls.version() is not None

    def setup(self) -> None:  # noqa: B027 - optional hook, deliberately not abstract
        """One-time initialisation such as loading models. Timed separately from extraction."""

    def warm_up(self) -> None:
        """Extract a tiny bundled PDF once, after ``setup`` and before timing starts.

        This moves one-off costs such as lazy imports, caches and model initialisation out of
        the first document's timing, without each extractor having to handle them.
        """
        with as_file(files("extraceval") / "assets" / "warmup.pdf") as path:
            self.extract(path)

    @abstractmethod
    def extract(self, path: Path) -> list[str]:
        """Return the text of the PDF at ``path``, one string per page."""
