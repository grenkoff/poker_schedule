"""Importing this package triggers every adapter module to register.

Keep this list in sync as new rooms come online; the scraper registry is
populated by import side-effect, which is clearer than runtime scanning
and works identically under Django, pytest, and the management command.
"""

from . import pokerok  # noqa: F401
