"""Template tags for the public tournament list."""

from django import template

from apps.tournaments.columns import Column
from apps.tournaments.models import Tournament

register = template.Library()


@register.simple_tag
def render_column(tournament: Tournament, column: Column) -> str:
    return column.formatter(tournament)


@register.filter
def dictlookup(mapping: dict, key: str):
    """Look up a value in a dict by a runtime key — Django templates cannot
    do `mapping[variable]` natively."""
    if mapping is None:
        return ""
    return mapping.get(key, "")
