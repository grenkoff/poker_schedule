"""Transport DTOs for scraper → upsert boundary.

Scrapers parse whatever a room serves us and return these normalized,
typed records. Everything on this side of the boundary is plain Python —
no Django ORM, no DB sessions — so fixtures and tests can construct DTOs
directly without touching the database.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, kw_only=True, slots=True)
class BlindLevelDTO:
    level: int
    small_blind: int
    big_blind: int
    ante: int = 0
    duration_minutes: int | None = None


@dataclass(frozen=True, kw_only=True, slots=True)
class TournamentDTO:
    """One scraped tournament.

    Field names mirror `apps.tournaments.models.Tournament`. Omitted fields
    here (like `source_kind`, `scraped_at`, `avg_entrants`, `verified_by_admin`)
    are set by the upsert layer or by batch jobs downstream.
    """

    external_id: str
    name: str

    game_type: str  # value from GameType.choices
    tournament_format: str  # value from TournamentFormat.choices
    table_size: str  # value from TableSize.choices

    buy_in_cents: int
    rake_cents: int = 0
    currency: str = "USD"
    starting_stack: int | None = None

    start_at: datetime  # must be timezone-aware
    late_reg_minutes: int | None = None
    blind_level_minutes: int | None = None
    estimated_duration_minutes: int | None = None

    final_table_size: int = 9
    blind_reset_at_final: bool = False
    blind_reset_level: int | None = None

    blind_levels: tuple[BlindLevelDTO, ...] = ()
    raw_payload: dict[str, Any] | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.start_at.tzinfo is None:
            raise ValueError(
                f"TournamentDTO.start_at must be timezone-aware (got {self.start_at!r})"
            )
        if self.buy_in_cents < 0 or self.rake_cents < 0:
            raise ValueError("buy_in_cents and rake_cents must be non-negative")
