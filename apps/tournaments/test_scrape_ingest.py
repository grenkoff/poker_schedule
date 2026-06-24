"""Tests for the scrape-ingest pipeline (ScrapedTournamentResource + the
`ingest_scraped_schedule` management command).

Covers: a scraped recurring definition becomes a master (matched on external_key,
marked scraped) with regenerated children and an applied blind structure;
re-ingesting updates rather than duplicates; a dry run writes nothing; a master
missing from a later feed is reported for review; and a bad reference aborts.
"""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.rooms.models import PokerRoom
from apps.tournaments.models import ScrapeRun, Tournament, TournamentSeries

EXTERNAL_KEY = "pokerok|scrape-test-daily|every_24_hours|127"


@pytest.fixture
def series():
    room = PokerRoom.objects.get(slug="pokerok")
    obj, _ = TournamentSeries.objects.get_or_create(
        room=room, slug="scrape-test", defaults={"name": "Scrape Test Series"}
    )
    return obj


def _feed_item(series, **overrides) -> dict:
    item = {
        "external_key": EXTERNAL_KEY,
        "room": series.room.name,
        "series": series.name,
        "name": "Scrape Test Daily $25",
        "game_type": "NLHE",
        "buy_in_without_rake": "23",
        "bounty_buyin": "0",
        "rake": "2",
        "guaranteed_dollars": 5000,
        "payout_percent": 15,
        "starting_stack": 10000,
        "starting_stack_bb": 100,
        "timezone": "Asia/Almaty",
        "starting_time": "2026-07-01 22:00",
        "late_reg_at": "2026-07-01 23:00",
        "late_registration_available": True,
        "late_reg_level": 12,
        "blind_interval_minutes": 10,
        "break_minutes": 5,
        "players_per_table": 9,
        "players_at_final_table": 9,
        "min_players": 2,
        "max_players": 1000,
        "re_entry": "unlimited",
        "bubble": "finalized_when_registration_closes",
        "periodicity": "every_24_hours",
        "weekdays": 127,
        "early_bird_type": None,
        "featured_final_table": False,
        "deal_making": None,
        "bounty_type": None,
        "min_bounty": None,
        "blind_levels": [
            {"level": 1, "small_blind": 50, "big_blind": 100, "ante": 0},
            {"level": 2, "small_blind": 100, "big_blind": 200, "ante": 25},
        ],
    }
    item.update(overrides)
    return item


def _write_feed(tmp_path, items) -> str:
    path = tmp_path / "feed.json"
    path.write_text(json.dumps(items))
    return str(path)


def _ingest(path, *, apply=False) -> str:
    out = StringIO()
    args = [path, "--apply"] if apply else [path]
    call_command("ingest_scraped_schedule", *args, stdout=out, stderr=out)
    return out.getvalue()


@pytest.mark.django_db
def test_ingest_creates_master_with_children_and_structure(tmp_path, series):
    path = _write_feed(tmp_path, [_feed_item(series)])
    _ingest(path, apply=True)

    master = Tournament.objects.get(external_key=EXTERNAL_KEY)
    assert master.source == Tournament.Source.SCRAPED
    assert master.verified_by_admin is False  # scraped rows wait for review
    assert master.last_seen_at is not None
    assert master.blind_levels.count() == 2

    children = Tournament.objects.filter(series_master=master)
    assert children.exists()  # recurring children regenerated
    assert children.first().blind_levels.count() == 2  # structure copied down


@pytest.mark.django_db
def test_ingest_is_idempotent(tmp_path, series):
    path = _write_feed(tmp_path, [_feed_item(series)])
    _ingest(path, apply=True)
    _ingest(path, apply=True)

    assert Tournament.objects.filter(external_key=EXTERNAL_KEY).count() == 1


@pytest.mark.django_db
def test_dry_run_writes_nothing(tmp_path, series):
    path = _write_feed(tmp_path, [_feed_item(series)])
    out = _ingest(path, apply=False)

    assert "DRY RUN" in out
    assert not Tournament.objects.filter(external_key=EXTERNAL_KEY).exists()


@pytest.mark.django_db
def test_unseen_master_reported_for_review(tmp_path, series):
    _ingest(_write_feed(tmp_path, [_feed_item(series)]), apply=True)
    out = _ingest(_write_feed(tmp_path, []), apply=True)

    assert "NOT in this feed" in out
    assert "Scrape Test Daily $25" in out
    # Not auto-deleted — left for the human to review.
    assert Tournament.objects.filter(external_key=EXTERNAL_KEY).exists()


@pytest.mark.django_db
def test_apply_records_scrape_run(tmp_path, series):
    _ingest(_write_feed(tmp_path, [_feed_item(series)]), apply=True)

    run = ScrapeRun.objects.latest("started_at")
    assert run.feed_size == 1
    assert run.created == 1
    assert run.missing_from_feed == 0


@pytest.mark.django_db
def test_dry_run_records_no_run(tmp_path, series):
    _ingest(_write_feed(tmp_path, [_feed_item(series)]), apply=False)
    assert ScrapeRun.objects.count() == 0


@pytest.mark.django_db
def test_stale_master_shown_under_admin_filter(admin_client, tmp_path, series):
    _ingest(_write_feed(tmp_path, [_feed_item(series)]), apply=True)
    _ingest(_write_feed(tmp_path, []), apply=True)  # later feed drops it → stale

    resp = admin_client.get("/admin/tournaments/tournament/?scrape_stale=stale")
    assert resp.status_code == 200
    assert b"Scrape Test Daily $25" in resp.content


@pytest.mark.django_db
def test_bad_series_aborts_without_writing(tmp_path, series):
    bad = _feed_item(series)
    bad["series"] = "No Such Series"
    path = _write_feed(tmp_path, [bad])

    with pytest.raises(CommandError):
        _ingest(path, apply=True)

    assert not Tournament.objects.filter(external_key=EXTERNAL_KEY).exists()
