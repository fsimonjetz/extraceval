"""Registry of available extractors.

Extractors are discovered through the ``extraceval.extractors`` entry-point group, which is how
both the built-in tools and third-party plugins are registered. ``register`` adds one at runtime,
e.g. from a notebook or a test.
"""

import logging
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import Any

from extraceval.extractors.base import Extractor, ExtractorOptions

__all__ = ["Extractor", "ExtractorOptions", "UnknownExtractorError", "get", "register", "registry"]

ENTRY_POINT_GROUP = "extraceval.extractors"

log = logging.getLogger(__name__)

_registry: dict[str, type[Extractor[Any]]] = {}
_discovered = False


class UnknownExtractorError(LookupError):
    def __init__(self, name: str) -> None:
        known = ", ".join(sorted(registry())) or "none"
        super().__init__(f"unknown extractor {name!r} (known: {known})")


def _discover() -> None:
    global _discovered
    if _discovered:
        return
    _discovered = True
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        if ep.name in _registry:
            continue
        try:
            _registry[ep.name] = ep.load()
        except Exception:
            log.warning("could not load extractor plugin %r (%s)", ep.name, ep.value, exc_info=True)


def register[E: type[Extractor[Any]]](name: str) -> Callable[[E], E]:
    """Class decorator registering an extractor under ``name``, overriding any existing one."""

    def decorator(cls: E) -> E:
        _discover()
        _registry[name] = cls
        return cls

    return decorator


def registry() -> dict[str, type[Extractor[Any]]]:
    """All known extractors by name, installed or not."""
    _discover()
    return dict(sorted(_registry.items()))


def get(name: str) -> type[Extractor[Any]]:
    try:
        return registry()[name]
    except KeyError:
        raise UnknownExtractorError(name) from None
