"""Pokerok (GGNetwork) scraper — fixture-backed in this MVP cycle.

Live Pokerok/GGPoker schedules can't be fetched from this codebase yet:
the public tournament lobby is a JS-rendered client-side app and the
domain blocks most datacenter IP ranges, which means both CI and Railway
egress fail on the live URL. Rather than ship an HTTP scraper that only
works from a laptop in-region, this adapter loads a curated JSON fixture
with realistic daily Pokerok tournaments. The rest of the pipeline —
upsert, admin, filters, PDF export — exercises the exact same DTO
contract, so swapping in a live parser later is a one-file change.

When we're ready for live HTTP:

  1. Replace `_load_fixture()` with an `httpx` call to whatever public
     endpoint returns the lobby data (likely JSON after sniffing the
     browser's XHRs on the tournament page).
  2. Keep `_to_dto()` identical — the shape is already correct.
  3. Swap this adapter's body to `_fetch_raw()` → `_to_dto()` and delete
     the fixture reference.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from apps.scrapers.base import BaseScraper
from apps.scrapers.dto import BlindLevelDTO, TournamentDTO
from apps.scrapers.registry import register

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "pokerok.json"


@register
class PokerokScraper(BaseScraper):
    room_slug = "pokerok"

    def fetch_schedule(self) -> list[TournamentDTO]:
        data = self._load_fixture()
        return [self._to_dto(item) for item in data["tournaments"]]

    @staticmethod
    def _load_fixture() -> dict[str, Any]:
        with FIXTURE_PATH.open(encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def _to_dto(item: dict[str, Any]) -> TournamentDTO:
        blind_levels = tuple(
            BlindLevelDTO(
                level=bl["level"],
                small_blind=bl["small_blind"],
                big_blind=bl["big_blind"],
                ante=bl.get("ante", 0),
                duration_minutes=bl.get("duration_minutes"),
            )
            for bl in item.get("blind_levels", [])
        )
        return TournamentDTO(
            external_id=item["id"],
            name=item["name"],
            game_type=item["game_type"],
            tournament_format=item["format"],
            table_size=item["table_size"],
            buy_in_cents=item["buy_in_cents"],
            rake_cents=item.get("rake_cents", 0),
            currency=item.get("currency", "USD"),
            starting_stack=item.get("starting_stack"),
            start_at=datetime.fromisoformat(item["start_at"]),
            late_reg_minutes=item.get("late_reg_minutes"),
            blind_level_minutes=item.get("blind_level_minutes"),
            estimated_duration_minutes=item.get("estimated_duration_minutes"),
            final_table_size=item.get("final_table_size", 9),
            blind_reset_at_final=item.get("blind_reset_at_final", False),
            blind_reset_level=item.get("blind_reset_level"),
            blind_levels=blind_levels,
            raw_payload=item,
        )
