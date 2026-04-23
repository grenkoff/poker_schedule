"""Base class for per-room scraper adapters.

Each concrete adapter lives in `apps.scrapers.adapters.<room>` and is
registered via `@register` so the management command and Celery tasks can
look it up by `room_slug`.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from .dto import TournamentDTO


class BaseScraper(ABC):
    """Contract every room adapter implements.

    `room_slug` must match `PokerRoom.slug` in the database so the upsert
    layer knows which room the DTOs belong to.
    """

    room_slug: ClassVar[str]

    @abstractmethod
    def fetch_schedule(self) -> list[TournamentDTO]:
        """Return the currently-advertised upcoming tournaments.

        Implementations should be side-effect free (no DB writes) and
        idempotent — `upsert_tournaments` handles persistence.
        """
