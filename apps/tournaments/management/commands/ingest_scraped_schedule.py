"""`manage.py ingest_scraped_schedule <file.json> [--apply]`

Ingest a normalized PokerOK schedule (produced by the standalone scraper that
runs on an isolated machine) into the tournament DB. This is the server-side
half of the scrape pipeline — the risky lobby-reading lives entirely off-server.

The file is a JSON list of recurring/one-off tournament *definitions*. Each is
matched on ``external_key`` via :class:`ScrapedTournamentResource`, so re-running
the same feed updates the same masters instead of creating duplicates; recurring
children are regenerated automatically. Blind levels are carried inline and
mapped onto reusable :class:`BlindStructureTemplate` rows (deduplicated by the
existing signature cache).

Defaults to a **dry run** (reports counts, writes nothing). Pass ``--apply`` to
commit. After applying, scraped masters whose ``external_key`` is absent from the
feed are reported as "not seen this run" for human review (never auto-deleted).

JSON shape (per item; keys are model field names):

    {
      "external_key": "pokerok|daily-special-25|2200|every_24_hours|127",
      "room": "Pokerok",
      "series": "Daily Guarantees",
      "name": "Daily Special $25",
      "game_type": "NLHE",
      "buy_in_without_rake": "23", "bounty_buyin": "0", "rake": "2",
      "guaranteed_dollars": 5000, "payout_percent": 15,
      "starting_stack": 10000, "starting_stack_bb": 100,
      "timezone": "Asia/Almaty",
      "starting_time": "2026-06-25 22:00", "late_reg_at": "2026-06-25 23:00",
      "late_registration_available": true, "late_reg_level": 12,
      "blind_interval_minutes": 10, "break_minutes": 5,
      "players_per_table": 9, "players_at_final_table": 9,
      "min_players": 2, "max_players": 1000,
      "re_entry": "unlimited", "bubble": "finalized_when_registration_closes",
      "periodicity": "every_24_hours", "weekdays": 127,
      "early_bird_type": null, "featured_final_table": false,
      "deal_making": null, "bounty_type": null, "min_bounty": null,
      "blind_levels": [{"level": 1, "small_blind": 50, "big_blind": 100, "ante": 0}, ...]
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import tablib
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from import_export.results import RowResult

from apps.tournaments.models import (
    BlindLevelTemplate,
    BlindStructureTemplate,
    Tournament,
    auto_template_name,
    blind_signature,
    template_id_for_signature,
)
from apps.tournaments.resources import ScrapedTournamentResource

# Recomputed on import (see TournamentResource.before_save_instance), so we send
# them blank — the cell value is ignored anyway.
_COMPUTED_FIELDS = {"buy_in_total", "is_bounty", "early_bird"}


class Command(BaseCommand):
    help = (
        "Ingest a scraped PokerOK schedule (JSON) into the tournament DB. "
        "Dry run by default; pass --apply to commit."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("path", help="Path to the scraped schedule JSON file.")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Commit the changes. Without this flag the command only reports a dry run.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        path = Path(options["path"])
        apply: bool = options["apply"]
        dry_run = not apply

        data = self._load(path)

        resource = ScrapedTournamentResource()
        field_order = list(resource._meta.fields)
        header_for = {fn: resource.fields[fn].column_name for fn in field_order}

        dataset = tablib.Dataset(headers=[header_for[fn] for fn in field_order])
        feed_keys: set[str] = set()

        for item in data:
            key = item.get("external_key")
            if not key:
                raise CommandError(f"Every item needs an external_key; offending item: {item!r}")
            feed_keys.add(key)
            # Templates are reference data; only create new ones when committing.
            template_name = self._ensure_template(item.get("blind_levels") or [], write=apply)
            dataset.append(self._row(item, field_order, template_name))

        result = resource.import_data(dataset, dry_run=dry_run, raise_errors=False)
        self._report(result, dry_run=dry_run)

        if result.has_errors() or result.has_validation_errors():
            raise CommandError(
                "Import reported errors; nothing was committed."
                if apply
                else "Dry run found errors — fix the feed before applying."
            )

        self._report_unseen(feed_keys)

    # --- helpers ---------------------------------------------------------

    def _load(self, path: Path) -> list[dict]:
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON: {exc}") from exc
        if not isinstance(data, list):
            raise CommandError("Top-level JSON must be a list of tournament objects.")
        return data

    def _row(self, item: dict, field_order: list[str], template_name: str | None) -> list:
        row = []
        for fn in field_order:
            if fn == "external_key":
                value: Any = item["external_key"]
            elif fn == "blind_structure":
                value = template_name or ""
            elif fn in _COMPUTED_FIELDS:
                value = ""  # recomputed on import
            else:
                value = item.get(fn)
                if value is None:
                    value = ""
            row.append(value)
        return row

    def _ensure_template(self, levels: list[dict], *, write: bool) -> str | None:
        """Return the name of the template matching ``levels``.

        Reuses an existing template (deduped by signature); creates one only when
        ``write`` is True. In dry-run with no existing match, returns None so the
        row imports without a (not-yet-created) template reference.
        """
        if not levels:
            return None
        level_objs = [
            SimpleNamespace(
                level=row["level"],
                small_blind=row["small_blind"],
                big_blind=row["big_blind"],
                ante=row.get("ante", 0),
            )
            for row in levels
        ]
        signature = blind_signature(level_objs)
        existing_id = template_id_for_signature(signature)
        if existing_id is not None:
            # filter().first() (not get()) guards against a stale signature cache
            # pointing at a row that no longer exists.
            existing = BlindStructureTemplate.objects.filter(pk=existing_id).first()
            if existing is not None:
                return existing.name
        if not write:
            return None
        name = auto_template_name(level_objs)[:120]
        with transaction.atomic():
            template = BlindStructureTemplate.objects.create(name=name)
            BlindLevelTemplate.objects.bulk_create(
                BlindLevelTemplate(
                    template=template,
                    level=obj.level,
                    small_blind=obj.small_blind,
                    big_blind=obj.big_blind,
                    ante=obj.ante,
                )
                for obj in level_objs
            )
        return template.name

    def _report(self, result, *, dry_run: bool) -> None:
        prefix = "DRY RUN — " if dry_run else ""
        created = result.totals[RowResult.IMPORT_TYPE_NEW]
        updated = result.totals[RowResult.IMPORT_TYPE_UPDATE]
        skipped = result.totals[RowResult.IMPORT_TYPE_SKIP]
        errored = result.totals[RowResult.IMPORT_TYPE_ERROR]
        invalid = result.totals[RowResult.IMPORT_TYPE_INVALID]
        self.stdout.write(
            f"{prefix}{created} created, {updated} updated, "
            f"{skipped} unchanged, {errored + invalid} with errors."
        )
        for err in result.base_errors:
            self.stderr.write(self.style.ERROR(f"  file: {err.error}"))
        for row in result.invalid_rows:
            self.stderr.write(self.style.ERROR(f"  row {row.number}: {row.error}"))
        for row in result.error_rows:
            for err in row.errors:
                self.stderr.write(self.style.ERROR(f"  row {row.number}: {err.error}"))

    def _report_unseen(self, feed_keys: set[str]) -> None:
        unseen = list(
            Tournament.objects.filter(
                source=Tournament.Source.SCRAPED,
                series_master__isnull=True,
            )
            .exclude(external_key__in=feed_keys)
            .values_list("external_key", "name")
        )
        if not unseen:
            return
        self.stdout.write(
            self.style.WARNING(
                f"{len(unseen)} scraped tournament(s) were NOT in this feed (review for removal):"
            )
        )
        for _key, name in unseen[:20]:
            self.stdout.write(f"  - {name}")
