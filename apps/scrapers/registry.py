"""Slug → scraper class registry.

Adapters call `@register` at import time. `apps.scrapers.adapters.__init__`
imports every adapter module to trigger registration on Django startup.
"""

from .base import BaseScraper

_REGISTRY: dict[str, type[BaseScraper]] = {}


def register(cls: type[BaseScraper]) -> type[BaseScraper]:
    slug = cls.room_slug
    if not slug:
        raise ValueError(f"{cls.__name__} is missing a room_slug")
    if slug in _REGISTRY and _REGISTRY[slug] is not cls:
        raise ValueError(
            f"Duplicate scraper for '{slug}': {_REGISTRY[slug].__name__} vs {cls.__name__}"
        )
    _REGISTRY[slug] = cls
    return cls


def get_scraper(slug: str) -> BaseScraper:
    if slug not in _REGISTRY:
        known = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise KeyError(f"No scraper registered for room '{slug}'. Registered: {known}.")
    return _REGISTRY[slug]()


def registered_slugs() -> list[str]:
    return sorted(_REGISTRY)
