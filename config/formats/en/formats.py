"""English-locale format overrides for this project.

Django's bundled `en` formats put `%Y-%m-%d` first in `DATE_INPUT_FORMATS`,
but the tournament admin date widget renders `dd.mm.yyyy`. Without this
override, the admin calendar JS reads the first format, fails to parse
"18.05.2026", and opens on a 1923 epoch fallback. Putting `%d.%m.%Y`
first fixes that.

Only the formats we care to change are listed here; everything else
falls through to Django's bundled `en` defaults.
"""

DATE_INPUT_FORMATS = [
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
]
TIME_INPUT_FORMATS = [
    "%H:%M",
    "%H:%M:%S",
    "%H:%M:%S.%f",
]
