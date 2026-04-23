"""Template filters for rendering tournament money fields.

Used by the list view and, later, the PDF export. Locale-aware formatting
(per-user decimal separator, grouping, etc.) can be layered on once we
wire user locales through — for now this sticks to a Western-style
thousand separator and a two-decimal amount.
"""

from decimal import Decimal

from django import template

register = template.Library()

_CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "RUB": "₽",
    "CNY": "¥",
    "JPY": "¥",
}


@register.filter
def money(cents: int | None, currency: str = "USD") -> str:
    """`{{ tournament.buy_in_cents|money:tournament.currency }}` → "$10.00".

    Unknown currencies are prefixed with their ISO code: "CAD 12.50".
    Known single-char symbols are prefixed directly: "$10.00".
    """
    if cents is None:
        return ""
    amount = Decimal(cents) / Decimal(100)
    formatted = f"{amount:,.2f}"
    symbol = _CURRENCY_SYMBOLS.get(currency.upper())
    if symbol:
        return f"{symbol}{formatted}"
    return f"{currency.upper()} {formatted}"
