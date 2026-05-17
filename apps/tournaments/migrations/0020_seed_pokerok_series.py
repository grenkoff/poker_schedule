from django.db import migrations
from django.utils.text import slugify


# (name, sort_order). Groups (Online / Featured / Weekly) only affect
# the numeric sort_order; we store a flat list per the design decision.
POKEROK_SERIES = [
    # Online Series
    ("WSOP Online", 10),
    ("WSOP Super Circuit Online", 20),
    ("GG World Festival", 30),
    ("Winter Giveaway Series", 40),
    ("GGMillion$ Week", 50),
    ("microFestival", 60),
    ("Bounty Hunters Series", 70),
    ("Omaholic Series", 80),
    ("Flip & Go Millionaire", 90),
    ("Black Friday Week", 100),
    ("GGMasters Freezeout Anniversary", 110),
    # Featured
    ("GGMasters", 200),
    ("GGMillion$", 210),
    ("WSOP Express", 220),
    ("Flip & Go", 230),
    ("The Weekender", 240),
    ("Flash Satellites", 250),
    ("Mystery Bounty", 260),
    # Weekly Schedules
    ("Daily Guarantees", 300),
    ("High Rollers", 310),
    ("Bounty Hunters", 320),
    ("Omaholic", 330),
    ("T$ Builder", 340),
    ("Chinese Zodiac", 350),
]


def seed(apps, schema_editor):
    PokerRoom = apps.get_model("rooms", "PokerRoom")
    TournamentSeries = apps.get_model("tournaments", "TournamentSeries")
    try:
        pokerok = PokerRoom.objects.get(slug="pokerok")
    except PokerRoom.DoesNotExist:
        return

    for name, order in POKEROK_SERIES:
        TournamentSeries.objects.update_or_create(
            room=pokerok,
            slug=slugify(name) or name.lower().replace(" ", "-"),
            defaults={"name": name, "sort_order": order},
        )


def unseed(apps, schema_editor):
    PokerRoom = apps.get_model("rooms", "PokerRoom")
    TournamentSeries = apps.get_model("tournaments", "TournamentSeries")
    try:
        pokerok = PokerRoom.objects.get(slug="pokerok")
    except PokerRoom.DoesNotExist:
        return
    slugs = [slugify(n) or n.lower().replace(" ", "-") for n, _ in POKEROK_SERIES]
    TournamentSeries.objects.filter(room=pokerok, slug__in=slugs).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tournaments", "0019_tournamentseries_image"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
