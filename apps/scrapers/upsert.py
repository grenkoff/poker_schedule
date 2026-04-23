"""Persistence layer for scraper output.

Scrapers produce `TournamentDTO`s; this module takes a batch and writes
them to the DB idempotently. The upsert key is `(room, external_id)`, so
running the same scrape twice is a no-op.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.rooms.models import PokerRoom
from apps.tournaments.models import BlindStructure, SourceKind, Tournament

from .dto import BlindLevelDTO, TournamentDTO


@dataclass(slots=True)
class UpsertStats:
    created: int = 0
    updated: int = 0

    @property
    def total(self) -> int:
        return self.created + self.updated


def upsert_tournaments(room: PokerRoom, dtos: Iterable[TournamentDTO]) -> UpsertStats:
    """Persist a batch of scraped tournaments for `room`.

    - `source_kind` is forced to SCRAPED; scraped rows can still be marked
      `verified_by_admin=True` from the admin without being reverted here
      (we never touch that flag).
    - `blind_levels`, when provided, replaces the existing rows wholesale
      for the tournament. This is simpler than diffing and correct for
      schedules that rarely change.
    - The whole batch runs in a single transaction so a partial failure
      rolls back cleanly.
    """
    stats = UpsertStats()
    now = timezone.now()

    with transaction.atomic():
        for dto in dtos:
            tournament, created = Tournament.objects.update_or_create(
                room=room,
                external_id=dto.external_id,
                defaults={
                    "name": dto.name,
                    "game_type": dto.game_type,
                    "tournament_format": dto.tournament_format,
                    "table_size": dto.table_size,
                    "buy_in_cents": dto.buy_in_cents,
                    "rake_cents": dto.rake_cents,
                    "currency": dto.currency,
                    "starting_stack": dto.starting_stack,
                    "start_at": dto.start_at,
                    "late_reg_minutes": dto.late_reg_minutes,
                    "blind_level_minutes": dto.blind_level_minutes,
                    "estimated_duration_minutes": dto.estimated_duration_minutes,
                    "final_table_size": dto.final_table_size,
                    "blind_reset_at_final": dto.blind_reset_at_final,
                    "blind_reset_level": dto.blind_reset_level,
                    "source_kind": SourceKind.SCRAPED,
                    "scraped_at": now,
                    "raw_payload": dto.raw_payload,
                },
            )
            if dto.blind_levels:
                _replace_blind_levels(tournament, dto.blind_levels)

            if created:
                stats.created += 1
            else:
                stats.updated += 1

    return stats


def _replace_blind_levels(tournament: Tournament, blind_levels: tuple[BlindLevelDTO, ...]) -> None:
    BlindStructure.objects.filter(tournament=tournament).delete()
    BlindStructure.objects.bulk_create(
        [
            BlindStructure(
                tournament=tournament,
                level=bl.level,
                small_blind=bl.small_blind,
                big_blind=bl.big_blind,
                ante=bl.ante,
                duration_minutes=bl.duration_minutes,
            )
            for bl in blind_levels
        ]
    )
