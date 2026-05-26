"""Bring BlindStructureTemplate names to the always-hashed canonical
form and merge templates that share a signature.

After 0030 the names already encoded first/last shape, but the hash
suffix was only present on collisions. The runtime now always appends
the hash so equal signatures produce equal names — which makes
identical structures observable as a name collision and lets us
collapse them into a single row here.

Templates with zero levels are skipped. Merging keeps the lowest-PK
template per signature and deletes the rest. Tournaments don't hold
FKs to templates (apply_to copies rows into `blind_levels`), so the
delete is safe.
"""

import hashlib

from django.db import migrations


def _format_int(n: int) -> str:
    return f"{n:,}"


def _signature(rows: list[tuple[int, int, int, int]]) -> tuple:
    return tuple(rows)


def _canonical_name(rows: list[tuple[int, int, int, int]]) -> str:
    first = rows[0]
    last = rows[-1]
    base = (
        f"{first[0]}-{_format_int(first[2])}({_format_int(first[3])})"
        f"_{last[0]}-{_format_int(last[2])}({_format_int(last[3])})"
    )
    digest = hashlib.sha256(repr(_signature(rows)).encode()).hexdigest()[:6]
    return f"{base} [{digest}]"


def collapse(apps, schema_editor):
    BlindStructureTemplate = apps.get_model("tournaments", "BlindStructureTemplate")
    BlindLevelTemplate = apps.get_model("tournaments", "BlindLevelTemplate")

    # Group templates by signature so duplicates land in the same bucket.
    by_sig: dict[tuple, list] = {}
    for tpl in BlindStructureTemplate.objects.all().order_by("pk"):
        rows = list(
            BlindLevelTemplate.objects.filter(template=tpl)
            .order_by("level")
            .values_list("level", "small_blind", "big_blind", "ante")
        )
        if not rows:
            continue
        by_sig.setdefault(_signature(rows), []).append((tpl, rows))

    # Build the final set of canonical names so we can rename without
    # tripping the unique constraint. Two-pass: first delete dup rows,
    # then rename surviving templates.
    survivors: list[tuple] = []
    for sig, group in by_sig.items():
        keeper_tpl, rows = group[0]
        survivors.append((keeper_tpl, rows))
        for stale_tpl, _ in group[1:]:
            stale_tpl.delete()

    # Stage the renames against a copy of the live name set so we can
    # detect (extremely unlikely) hash collisions between DIFFERENT
    # signatures and suffix them numerically.
    used_names: set[str] = set(
        BlindStructureTemplate.objects.exclude(pk__in=[t.pk for t, _ in survivors]).values_list(
            "name", flat=True
        )
    )
    for tpl, rows in survivors:
        canonical = _canonical_name(rows)
        candidate = canonical
        n = 2
        while candidate in used_names:
            candidate = f"{canonical} ({n})"
            n += 1
        used_names.add(candidate)
        if tpl.name != candidate:
            tpl.name = candidate[:120]
            tpl.save(update_fields=["name", "updated_at"])


def noop_reverse(apps, schema_editor):
    # Deleted templates and original free-form names are not
    # recoverable; leave the canonical state in place on rollback.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0030_rename_templates_to_content_form"),
    ]

    operations = [
        migrations.RunPython(collapse, noop_reverse),
    ]
