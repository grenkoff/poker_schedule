"""Custom XLSX export format that hardens the hand-editable tournament file.

`django-import-export` produces a plain xlsx via tablib; tablib can't lock cells
or attach dropdowns. So this format runs the tablib output back through openpyxl
to add two editor affordances, then hands the bytes onward unchanged:

* The ``id`` column and the header row are locked (sheet protection on, every
  other cell — plus a buffer of empty rows for new tournaments — left editable).
  ``id`` is the import match key (see ``TournamentResource.import_id_fields``);
  hand-editing it silently overwrites the wrong row, and renaming a header
  breaks the column→field mapping, so both are made read-only.
* Columns backed by a fixed option set get a data-validation dropdown listing the
  exact strings import accepts — FK columns export the option ``name`` slug,
  ``game_type`` exports the choice code. The option values live on a hidden
  helper sheet so we're not bound by the 255-char inline-list limit.

Import is untouched: the parsing path (`create_dataset`) ignores protection and
validation, so a file produced here round-trips through import unchanged.
"""

from __future__ import annotations

from io import BytesIO

from import_export.formats import base_formats

# Columns whose valid values are a closed set. `series` is deliberately absent:
# its options depend on the row's `room`, so a flat dropdown would offer
# wrong-room series. Booleans are absent too — they export as "1"/"0".
_DROPDOWN_COLUMNS = (
    "room",
    "game_type",
    "re_entry",
    "bubble",
    "periodicity",
    "bounty_type",
    "early_bird_type",
    "deal_making",
)

# Extra empty rows below the data kept editable (and dropdown-equipped) so an
# editor can append new tournaments under a protected sheet.
_EXTRA_ROWS = 200


def _dropdown_options() -> dict[str, list[str]]:
    """Allowed cell strings per dropdown column, in display order.

    Imported lazily so this module stays import-safe before the app registry is
    ready (it's referenced from admin at class-definition time).
    """
    from apps.rooms.models import PokerRoom

    from .models import (
        BountyOption,
        BubbleOption,
        DealMakingOption,
        EarlyBirdType,
        GameType,
        Periodicity,
        ReEntryOption,
    )

    def _names(model) -> list[str]:
        return list(model.objects.order_by("sort_order", "label").values_list("name", flat=True))

    return {
        "room": list(PokerRoom.objects.order_by("name").values_list("name", flat=True)),
        "game_type": [choice.value for choice in GameType],
        "re_entry": _names(ReEntryOption),
        "bubble": _names(BubbleOption),
        "periodicity": _names(Periodicity),
        "bounty_type": _names(BountyOption),
        "early_bird_type": _names(EarlyBirdType),
        "deal_making": _names(DealMakingOption),
    }


def _harden_workbook(content: bytes) -> bytes:
    import openpyxl
    from openpyxl.styles import Protection
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = openpyxl.load_workbook(BytesIO(content))
    ws = wb.active

    headers = [cell.value for cell in ws[1]]
    col_of = {name: idx + 1 for idx, name in enumerate(headers) if name}
    last_row = ws.max_row + _EXTRA_ROWS

    # --- dropdowns on closed-set columns ---------------------------------
    options = _dropdown_options()
    lists = wb.create_sheet("lists")
    lists.sheet_state = "hidden"
    for list_col, column_name in enumerate(_DROPDOWN_COLUMNS, start=1):
        values = options.get(column_name)
        target_col = col_of.get(column_name)
        if not values or not target_col:
            continue
        letter = get_column_letter(list_col)
        lists.cell(row=1, column=list_col, value=column_name)
        for offset, value in enumerate(values, start=2):
            lists.cell(row=offset, column=list_col, value=value)
        ref = f"lists!${letter}$2:${letter}${len(values) + 1}"
        dv = DataValidation(type="list", formula1=ref, allow_blank=True)
        ws.add_data_validation(dv)
        target_letter = get_column_letter(target_col)
        dv.add(f"{target_letter}2:{target_letter}{last_row}")

    # --- lock id + header, leave everything else editable ----------------
    id_col = col_of.get("id")
    unlocked = Protection(locked=False)
    locked = Protection(locked=True)
    for row in range(1, last_row + 1):
        for col in range(1, len(headers) + 1):
            is_header = row == 1
            is_id = col == id_col
            ws.cell(row=row, column=col).protection = locked if (is_header or is_id) else unlocked
    ws.protection.sheet = True

    out = BytesIO()
    wb.save(out)
    return out.getvalue()


class LockedDropdownXLSX(base_formats.XLSX):
    """XLSX export with a locked ``id``/header and option dropdowns.

    Inherits the import path unchanged; only the export bytes are reworked.
    """

    def export_data(self, dataset, **kwargs):
        content = super().export_data(dataset, **kwargs)
        return _harden_workbook(content)
