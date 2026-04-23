"""Tests for rooms models and the seed data migration."""

import pytest
from django.db import IntegrityError

from apps.rooms.models import Network, PokerRoom


@pytest.mark.django_db
def test_network_str_is_name():
    network = Network.objects.create(name="Test Net", slug="test-net")
    assert str(network) == "Test Net"


@pytest.mark.django_db
def test_network_slug_is_unique():
    Network.objects.create(name="A", slug="same")
    with pytest.raises(IntegrityError):
        Network.objects.create(name="B", slug="same")


@pytest.mark.django_db
def test_poker_room_requires_network():
    network = Network.objects.create(name="Net", slug="net")
    room = PokerRoom.objects.create(name="Room", slug="room", network=network)
    assert room.network == network
    assert str(room) == "Room"
    assert room.is_active is True


@pytest.mark.django_db
def test_poker_room_protects_network_from_cascade_delete():
    network = Network.objects.create(name="Net", slug="net")
    PokerRoom.objects.create(name="Room", slug="room", network=network)
    from django.db.models import ProtectedError

    with pytest.raises(ProtectedError):
        network.delete()


@pytest.mark.django_db
def test_seed_migration_creates_mvp_rooms():
    """The 0002 data migration should have seeded 3 MVP rooms."""
    slugs = set(PokerRoom.objects.values_list("slug", flat=True))
    assert {"pokerok", "pokerstars", "pokerdom"} <= slugs
