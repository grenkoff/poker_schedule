"""Unit tests for form helpers in apps/tournaments/forms.py.

These tests exercise clean_ante() and WeekdaysBitmaskField directly,
without hitting the database.
"""

from apps.tournaments.forms import BlindLevelTemplateInlineForm, WeekdaysBitmaskField


def test_clean_ante_blank_becomes_zero():
    form = BlindLevelTemplateInlineForm(
        data={"level": "1", "small_blind": "25", "big_blind": "50", "ante": ""}
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["ante"] == 0


def test_clean_ante_preserves_nonzero_value():
    form = BlindLevelTemplateInlineForm(
        data={"level": "1", "small_blind": "25", "big_blind": "50", "ante": "12"}
    )
    assert form.is_valid(), form.errors
    assert form.cleaned_data["ante"] == 12


def test_weekdays_pack_selection():
    field = WeekdaysBitmaskField()
    result = field.clean(["0", "1", "2"])  # Mon, Tue, Wed
    assert result == 0b0000111


def test_weekdays_prepare_value_from_int():
    field = WeekdaysBitmaskField()
    result = field.prepare_value(0b0000111)  # Mon=0, Tue=1, Wed=2
    assert set(result) == {"0", "1", "2"}


def test_weekdays_has_changed_same_bitmask():
    field = WeekdaysBitmaskField()
    assert not field.has_changed(0b0000111, ["0", "1", "2"])


def test_weekdays_has_changed_different_bitmask():
    field = WeekdaysBitmaskField()
    assert field.has_changed(0b0000111, ["0", "1"])
