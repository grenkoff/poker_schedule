"""`manage.py scrape_room <slug> [--dry-run]`

Looks up the adapter for `slug` via the scraper registry, fetches the
schedule, and upserts it. The `--dry-run` flag parses the payload but
touches no DB rows — useful when validating a new adapter or a live
site's HTML changed overnight.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.rooms.models import PokerRoom
from apps.scrapers.registry import get_scraper, registered_slugs
from apps.scrapers.upsert import upsert_tournaments


class Command(BaseCommand):
    help = "Fetch a poker room's tournament schedule and upsert it into the DB."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "room_slug",
            help="slug of the PokerRoom to scrape (e.g. 'pokerok').",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and print a summary but do not write to the database.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        room_slug: str = options["room_slug"]
        dry_run: bool = options["dry_run"]

        try:
            room = PokerRoom.objects.get(slug=room_slug)
        except PokerRoom.DoesNotExist as exc:
            raise CommandError(
                f"No PokerRoom with slug={room_slug!r}. "
                f"Check the rooms/pokerrom/ admin or the seed migration."
            ) from exc

        try:
            scraper = get_scraper(room_slug)
        except KeyError as exc:
            known = ", ".join(registered_slugs()) or "(none)"
            raise CommandError(
                f"No scraper registered for '{room_slug}'. Registered: {known}."
            ) from exc

        self.stdout.write(f"Fetching {room.name} schedule…")
        dtos = scraper.fetch_schedule()
        self.stdout.write(f"  {len(dtos)} tournament(s) returned.")

        if dry_run:
            self.stdout.write(self.style.WARNING("--dry-run: not writing to DB."))
            for dto in dtos:
                self.stdout.write(
                    f"  - {dto.external_id:40s} "
                    f"{dto.name:30s} "
                    f"${dto.buy_in_cents / 100:>7.2f} "
                    f"{dto.start_at:%Y-%m-%d %H:%M %Z}"
                )
            return

        stats = upsert_tournaments(room, dtos)
        self.stdout.write(
            self.style.SUCCESS(f"Upserted: {stats.created} created, {stats.updated} updated.")
        )
