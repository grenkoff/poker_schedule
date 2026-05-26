"""Rename every existing BlindStructureTemplate to the content-based
shape produced by `auto_template_name`.

Templates created before this migration carried free-form names
(`Like Daily Hyper $1`, hand-typed `jkjkj`, the space-separated draft
form, etc.). The runtime auto-name has stabilised on
`{first_level}-{first_bb}({first_ante})_{last_level}-{last_bb}({last_ante})`
with a 6-char hex `[hash]` suffix when two structures share that
shape. This pass brings the library in line so the dropdown is
internally consistent.

Templates with zero levels are skipped — they have no shape to encode.
"""

import hashlib
import re

from django.db import migrations


def _format_int(n: int) -> str:
    return f"{n:,}"


def _content_name(rows: list[tuple[int, int, int, int]]) -> str:
    first = rows[0]
    last = rows[-1]
    return (
        f"{first[0]}-{_format_int(first[2])}({_format_int(first[3])})"
        f"_{last[0]}-{_format_int(last[2])}({_format_int(last[3])})"
    )


def _signature(rows: list[tuple[int, int, int, int]]) -> tuple:
    return tuple(rows)


def _hash_suffix(rows: list[tuple[int, int, int, int]]) -> str:
    return hashlib.sha256(repr(_signature(rows)).encode()).hexdigest()[:6]


_CONTENT_RE = re.compile(
    r"^\d+-[\d,]+\(\d[\d,]*\)_\d+-[\d,]+\(\d[\d,]*\)(?: \[[a-f0-9]{6}\])?$"
)


def rename(apps, schema_editor):
    BlindStructureTemplate = apps.get_model("tournaments", "BlindStructureTemplate")
    BlindLevelTemplate = apps.get_model("tournaments", "BlindLevelTemplate")

    # Snapshot existing names to detect collisions while we rename. We
    # cannot just rely on `filter(name=...).exists()` because we'd race
    # against the renames we're about to do.
    used_names: set[str] = set(BlindStructureTemplate.objects.values_list("name", flat=True))

    templates = list(
        BlindStructureTemplate.objects.all().order_by("pk").prefetch_related("levels")
    )
    for tpl in templates:
        rows = list(
            BlindLevelTemplate.objects.filter(template=tpl)
            .order_by("level")
            .values_list("level", "small_blind", "big_blind", "ante")
        )
        if not rows:
            continue

        if _CONTENT_RE.match(tpl.name):
            # Already in the new shape — leave it alone.
            continue

        base = _content_name(rows)
        candidate = base
        # Allow another template (different signature) to already hold
        # `base`; in that case we MUST disambiguate with the hash.
        if candidate in used_names and candidate != tpl.name:
            candidate = f"{base} [{_hash_suffix(rows)}]"
        # As a last resort if hash also collides (extremely unlikely),
        # walk a numeric suffix.
        n = 2
        original_candidate = candidate
        while candidate in used_names and candidate != tpl.name:
            candidate = f"{original_candidate} ({n})"
            n += 1

        if candidate != tpl.name:
            used_names.discard(tpl.name)
            used_names.add(candidate)
            tpl.name = candidate[:120]
            tpl.save(update_fields=["name", "updated_at"])


def noop_reverse(apps, schema_editor):
    # The old names are not recoverable from the new shape. Leave the
    # current (renamed) state in place if someone walks the migration
    # backwards — they're still valid names, just not the originals.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("tournaments", "0029_alter_tournament_early_bird_type"),
    ]

    operations = [
        migrations.RunPython(rename, noop_reverse),
    ]
