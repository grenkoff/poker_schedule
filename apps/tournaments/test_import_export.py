"""Excel round-trip of tournaments via TournamentResource (django-import-export).

Covers: export uses human-readable FK values, import creates rows and recomputes
the derived columns (buy_in_total / is_bounty / early_bird / verified_by_admin),
import updates by id without duplicating, a clean round-trip reports no errors, and
a series that belongs to a different room is rejected as a row error.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
import tablib
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.rooms.models import Network, PokerRoom
from apps.tournaments.models import (
    BountyOption,
    BubbleOption,
    EarlyBirdType,
    GameType,
    Periodicity,
    ReEntryOption,
    Tournament,
    TournamentSeries,
)
from apps.tournaments.resources import TournamentResource

User = get_user_model()


@pytest.fixture
def superuser():
    return User.objects.create_superuser(username="ie_admin", email="ie@example.com", password="x")


@pytest.fixture
def series():
    room = PokerRoom.objects.get(slug="pokerok")
    obj, _ = TournamentSeries.objects.get_or_create(
        room=room, slug="ie-series", defaults={"name": "IE Series"}
    )
    return obj


def _make_tournament(series, **overrides) -> Tournament:
    fields = dict(
        room=series.room,
        series=series,
        name="Daily NLHE",
        game_type=GameType.NLHE,
        buy_in_total=Decimal("55.00"),
        buy_in_without_rake=Decimal("50.00"),
        bounty_buyin=Decimal("0"),
        rake=Decimal("5.00"),
        guaranteed_dollars=10000,
        payout_percent=15,
        starting_stack=10000,
        starting_stack_bb=50,
        starting_time=timezone.now() + timedelta(hours=1),
        late_reg_at=timezone.now() + timedelta(hours=2),
        late_reg_level=12,
        blind_interval_minutes=10,
        break_minutes=5,
        players_per_table=9,
        players_at_final_table=9,
        min_players=2,
        max_players=1000,
        re_entry=ReEntryOption.objects.get(name="unlimited"),
        bubble=BubbleOption.objects.get(name="finalized_when_registration_closes"),
        early_bird=True,
        early_bird_type=EarlyBirdType.objects.get(name="compensated_at_bubble"),
        featured_final_table=False,
        periodicity=Periodicity.objects.get(name="one_off"),
        verified_by_admin=True,
    )
    fields.update(overrides)
    return Tournament.objects.create(**fields)


def _export_dataset(user, queryset) -> tablib.Dataset:
    return TournamentResource(user=user).export(queryset)


def _row_as_dict(dataset: tablib.Dataset, index: int = 0) -> dict:
    return dict(dataset.dict[index])


def _dataset_from_rows(rows: list[dict]) -> tablib.Dataset:
    ds = tablib.Dataset(headers=list(rows[0].keys()))
    for row in rows:
        ds.append(list(row.values()))
    return ds


@pytest.mark.django_db
def test_admin_import_export_pages_render(admin_client):
    # The ImportExportMixin adds these views; a 200 confirms the buttons are wired.
    assert admin_client.get("/admin/tournaments/tournament/import/").status_code == 200
    assert admin_client.get("/admin/tournaments/tournament/export/").status_code == 200


@pytest.mark.django_db
def test_export_returns_rows(superuser, series):
    t = _make_tournament(series)
    ds = _export_dataset(superuser, Tournament.objects.filter(pk=t.pk))

    assert "room" in ds.headers and "series" in ds.headers
    row = _row_as_dict(ds)
    # Foreign keys are exported as the names an editor types, not ids.
    assert row["room"] == series.room.name
    assert row["series"] == series.name


@pytest.mark.django_db
def test_import_creates_tournament(superuser, series):
    template = _make_tournament(series)
    ds = _export_dataset(superuser, Tournament.objects.filter(pk=template.pk))
    row = _row_as_dict(ds)
    row["id"] = ""  # blank id → create
    row["name"] = "Imported NLHE"
    row["buy_in_total"] = "999.00"  # deliberately wrong; must be recomputed

    result = TournamentResource(user=superuser).import_data(_dataset_from_rows([row]), dry_run=False)
    assert not result.has_errors(), result.row_errors()

    created = Tournament.objects.get(name="Imported NLHE")
    assert created.pk != template.pk
    # buy_in_total recomputed from parts (50 + 0 + 5), ignoring the bad cell.
    assert created.buy_in_total == Decimal("55.00")
    assert created.early_bird is True  # early_bird_type was set
    assert created.is_bounty is False  # no bounty_type
    assert created.verified_by_admin is True  # imported by a superuser


@pytest.mark.django_db
def test_import_derives_is_bounty(superuser, series):
    template = _make_tournament(series)
    ds = _export_dataset(superuser, Tournament.objects.filter(pk=template.pk))
    row = _row_as_dict(ds)
    row["id"] = ""
    row["name"] = "Bounty NLHE"
    row["bounty_buyin"] = "10.00"
    row["bounty_type"] = BountyOption.objects.first().name

    result = TournamentResource(user=superuser).import_data(_dataset_from_rows([row]), dry_run=False)
    assert not result.has_errors(), result.row_errors()

    created = Tournament.objects.get(name="Bounty NLHE")
    assert created.is_bounty is True


@pytest.mark.django_db
def test_import_updates_by_id(superuser, series):
    t = _make_tournament(series)
    ds = _export_dataset(superuser, Tournament.objects.filter(pk=t.pk))
    row = _row_as_dict(ds)
    row["name"] = "Renamed"

    before = Tournament.objects.count()
    result = TournamentResource(user=superuser).import_data(_dataset_from_rows([row]), dry_run=False)
    assert not result.has_errors(), result.row_errors()

    assert Tournament.objects.count() == before  # updated, not duplicated
    t.refresh_from_db()
    assert t.name == "Renamed"


@pytest.mark.django_db
def test_round_trip(superuser, series):
    _make_tournament(series, name="A")
    _make_tournament(series, name="B")
    ds = _export_dataset(superuser, Tournament.objects.all())

    before = Tournament.objects.count()
    result = TournamentResource(user=superuser).import_data(ds, dry_run=False)

    assert not result.has_errors(), result.row_errors()
    assert Tournament.objects.count() == before  # unchanged rows, no new ones


@pytest.mark.django_db
def test_import_bad_series_row_errors(superuser, series):
    # A series that belongs to a *different* room must not resolve for pokerok.
    other_net, _ = Network.objects.get_or_create(slug="othernet", defaults={"name": "OtherNet"})
    other_room = PokerRoom.objects.create(
        name="OtherRoom", slug="otherroom", network=other_net
    )
    TournamentSeries.objects.create(room=other_room, slug="foreign", name="Foreign Series")

    template = _make_tournament(series)
    ds = _export_dataset(superuser, Tournament.objects.filter(pk=template.pk))
    row = _row_as_dict(ds)
    row["id"] = ""
    row["name"] = "Cross-room"
    row["series"] = "Foreign Series"  # exists, but not in pokerok

    result = TournamentResource(user=superuser).import_data(_dataset_from_rows([row]), dry_run=True)
    # A widget ValueError surfaces as a per-row validation error, which blocks
    # the import (the row is reported back to the editor rather than created).
    assert result.has_validation_errors()
    assert result.invalid_rows[0].error_count == 1
