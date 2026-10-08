"""
Keeping exported files from running code when they are opened in a spreadsheet program ("CSV injection" / "formula injection").

Why. Text that people typed (a file name, a review note, an institution or user name, anything an audit entry quotes) ends up in the CSV and Excel
files the application lets people download. A cell whose text begins with `=`, `+`, `-` or `@` (or a tab or carriage return) is read by Excel and
LibreOffice as a FORMULA, and a formula can read other cells, call out to the network or start programs. Whoever types such text, an institution user
for example, could then act inside an analyst's or an administrator's spreadsheet program the moment the export is opened.

Two kinds of output, two remedies.
* CSV has no cell types, so the text is made harmless by putting an apostrophe in front, the long-standing convention that spreadsheet programs read as
  "this is text" (`csv_safe`). Numbers, empty cells and text that is only a number (`-12.5`, `+255`, `1e5`) are left alone, so figures that other
  programs read from the file (a GIS, a script) are not changed.
* Excel files have cell types. openpyxl turns a string that begins with `=` into a formula cell; `text_cell` writes it as a text cell instead, and the
  words stay exactly as typed (no apostrophe shows).
"""
import re

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
_PLAIN_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def needs_neutralising(value) -> bool:
    """True for text a spreadsheet program could take for a formula."""
    return isinstance(value, str) and value.startswith(_FORMULA_STARTS) and not _PLAIN_NUMBER.match(value)


def csv_safe(value):
    """The value for a CSV cell: text that could be a formula gets an apostrophe in front; anything else is returned as it is."""
    return "'" + value if needs_neutralising(value) else value


def csv_safe_row(row) -> list:
    return [csv_safe(v) for v in row]


def text_cell(ws, row: int, column: int, value):
    """Write a value into an Excel worksheet; text that could be a formula is stored as plain text (not as a formula)."""
    cell = ws.cell(row=row, column=column, value=value)
    if isinstance(value, str) and value.startswith(_FORMULA_STARTS):
        cell.data_type = "s"
    return cell
