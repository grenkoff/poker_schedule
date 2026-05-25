"""Seed BlindStructureTemplate from existing tournaments.

Group every master tournament (`series_master__isnull=True`) by the
normalized signature of its blind levels, then create one named
template per unique signature. Children of recurring series share the
master's structure, so iterating masters is sufficient and avoids
N-fold duplicates.

Templates created here are auto-named "Like <tournament name>" so the
editor can recognize their shape at a glance. The `description` field
carries the audit marker that the reverse migration targets — manual
renames in admin therefore don't break unseed.
"""

from django.db import migrations


_DESC_PREFIX = "Auto-extracted on migration from "


def extract(apps, schema_editor):
    Tournament = apps.get_model("tournaments", "Tournament")
    BlindStructureTemplate = apps.get_model("tournaments", "BlindStructureTemplate")
    BlindLevelTemplate = apps.get_model("tournaments", "BlindLevelTemplate")

    sig_to_source: dict[tuple, object] = {}
    masters = Tournament.objects.filter(series_master__isnull=True).prefetch_related(
        "blind_levels"
    )
    for tournament in masters:
        rows = tuple(
            (lvl.level, lvl.small_blind, lvl.big_blind, lvl.ante)
            for lvl in sorted(tournament.blind_levels.all(), key=lambda r: r.level)
        )
        if not rows:
            continue
        # First master wins → naming is stable across re-runs that hit
        # the same DB snapshot.
        sig_to_source.setdefault(rows, tournament)

    for rows, source in sig_to_source.items():
        base = f"Like {source.name}"[:120]
        name = base
        n = 2
        while BlindStructureTemplate.objects.filter(name=name).exists():
            suffix = f" ({n})"
            name = base[: 120 - len(suffix)] + suffix
            n += 1
        template = BlindStructureTemplate.objects.create(
            name=name,
            description=f"{_DESC_PREFIX}'{source.name}'",
        )
        BlindLevelTemplate.objects.bulk_create(
            BlindLevelTemplate(
                template=template,
                level=lvl,
                small_blind=sb,
                big_blind=bb,
                ante=ante,
            )
            for (lvl, sb, bb, ante) in rows
        )


def unextract(apps, schema_editor):
    BlindStructureTemplate = apps.get_model("tournaments", "BlindStructureTemplate")
    BlindStructureTemplate.objects.filter(description__startswith=_DESC_PREFIX).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("tournaments", "0025_blindstructuretemplate_blindleveltemplate"),
    ]

    operations = [
        migrations.RunPython(extract, unextract),
    ]
