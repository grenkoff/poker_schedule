from django.db import migrations

SEED = [
    # (network_name, network_slug, network_site, room_name, room_slug, room_site)
    (
        "GGNetwork",
        "ggnetwork",
        "https://ggnetwork.com",
        "Pokerok",
        "pokerok",
        "https://pokerok.com",
    ),
    (
        "PokerStars",
        "pokerstars",
        "https://www.pokerstars.com",
        "PokerStars",
        "pokerstars",
        "https://www.pokerstars.com",
    ),
    (
        "PokerDom",
        "pokerdom",
        "https://pokerdom.com",
        "PokerDom",
        "pokerdom",
        "https://pokerdom.com",
    ),
]


def seed(apps, _schema_editor):
    Network = apps.get_model("rooms", "Network")
    PokerRoom = apps.get_model("rooms", "PokerRoom")
    for net_name, net_slug, net_site, room_name, room_slug, room_site in SEED:
        network, _ = Network.objects.update_or_create(
            slug=net_slug,
            defaults={"name": net_name, "website": net_site},
        )
        PokerRoom.objects.update_or_create(
            slug=room_slug,
            defaults={
                "name": room_name,
                "network": network,
                "website": room_site,
                "is_active": True,
            },
        )


def unseed(apps, _schema_editor):
    PokerRoom = apps.get_model("rooms", "PokerRoom")
    Network = apps.get_model("rooms", "Network")
    slugs = [item[4] for item in SEED]
    net_slugs = [item[1] for item in SEED]
    PokerRoom.objects.filter(slug__in=slugs).delete()
    Network.objects.filter(slug__in=net_slugs).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("rooms", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, reverse_code=unseed),
    ]
