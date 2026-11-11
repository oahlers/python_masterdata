"""Lossless writer for the Sæther MASTERDATA Excel template.

Only cell payloads and the style references of generated product rows in
``Master template`` are changed.  The XLSX package is otherwise copied
entry-for-entry, which preserves all sheets, formulas, comments, data
validations, extension lists and other template parts.  The authoritative
product-row style is read from row 5 of the untouched reference template and
applied to every generated row.  Example values in rows 5 and 6 are cleared in
the generated copy; neither source workbook is ever modified.
"""

from __future__ import annotations

import os
import re
import tempfile
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from html import escape
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

from app.masterdata_builder import MasterDataBuilder
from app.masterdata_model import MasterDataRecord


DEFAULT_TEMPLATE_PATH = Path("templates/saether_masterdata_template.xlsx")
DEFAULT_REFERENCE_TEMPLATE_PATH = Path(
    "templates/saether_masterdata_template_reference.xlsx"
)
MASTER_SHEET_NAME = "Master template"
FIRST_OUTPUT_ROW = 5
EXAMPLE_ROWS = (5, 6)
AUTHORITATIVE_STYLE_ROW = 5

DOCUMENT_REL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

# Formula columns D, F and H are intentionally not in this map.
CELL_FIELDS: Mapping[str, str] = {
    "A": "copy_from_item_number",
    "B": "item_number",
    "C": "m3_name",
    "E": "m3_description",
    "G": "receipt_text",
    "I": "item_type",
    "J": "item_group",
    "K": "item_group_description",
    "L": "product_group",
    "M": "product_line",
    "N": "item_category",
    "O": "ref_number",
    "P": "ean",
    "Q": "edition",
    "R": "net_content",
    "S": "content_unit",
    "T": "delivery_week",
    "U": "supplier_number_for_pos",
    "V": "gender",
    "W": "distribution_channel",
    "X": "cogs",
    "Y": "rrp_dkk",
    "Z": "rrp_sek",
    "AA": "rrp_nok",
    "AB": "rrp_eur",
}


class MasterDataExcelExporter:
    """Write records into a copy of the existing MASTERDATA template."""

    def __init__(
        self,
        template_path: str | Path = DEFAULT_TEMPLATE_PATH,
        *,
        reference_template_path: str | Path = DEFAULT_REFERENCE_TEMPLATE_PATH,
        sheet_name: str = MASTER_SHEET_NAME,
        first_output_row: int = FIRST_OUTPUT_ROW,
        authoritative_style_row: int = AUTHORITATIVE_STYLE_ROW,
    ) -> None:
        self.template_path = Path(template_path)
        self.reference_template_path = Path(reference_template_path)
        self.sheet_name = sheet_name
        self.first_output_row = first_output_row
        self.authoritative_style_row = authoritative_style_row

    def export(
        self,
        records: Iterable[MasterDataRecord],
        output_path: str | Path,
    ) -> Path:
        records = list(records)
        if not records:
            raise ValueError("At least one MasterDataRecord is required")
        missing_item_numbers = [
            index
            for index, record in enumerate(records, start=1)
            if record.item_number is None or not str(record.item_number).strip()
        ]
        if missing_item_numbers:
            positions = ", ".join(str(index) for index in missing_item_numbers)
            raise ValueError(
                "item_number is required for MASTERDATA export "
                f"(record(s): {positions})"
            )
        if self.first_output_row < FIRST_OUTPUT_ROW:
            raise ValueError(
                "first_output_row must be 5 or later"
            )
        if not self.template_path.is_file():
            raise FileNotFoundError(
                f"MASTERDATA template was not found: {self.template_path}"
            )

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(self.template_path, "r") as source_zip:
            sheet_part = _sheet_part_name(
                source_zip, self.sheet_name
            )
            worksheet_xml = source_zip.read(sheet_part)

            reference_path = (
                self.reference_template_path
                if self.reference_template_path.is_file()
                else self.template_path
            )
            with zipfile.ZipFile(reference_path, "r") as reference_zip:
                reference_sheet_part = _sheet_part_name(
                    reference_zip,
                    self.sheet_name,
                )
                reference_worksheet_xml = reference_zip.read(
                    reference_sheet_part
                )
                # Style ids are workbook-local.  The current production and
                # reference templates are expected to share styles.xml because
                # the clean template was made from the reference workbook.  A
                # custom/test template may not; in that case its own row 5 is
                # the only safe authoritative style source.
                if (
                    reference_zip.read("xl/styles.xml")
                    != source_zip.read("xl/styles.xml")
                ):
                    reference_worksheet_xml = worksheet_xml

            workbook_xml = _normalize_calculation_properties(
                source_zip.read("xl/workbook.xml")
            )

            authoritative_format = _authoritative_row_format(
                reference_worksheet_xml,
                self.authoritative_style_row,
            )
            # The workbook's two example products are documentation only.  Clear
            # their product payloads in the output copy before writing approved
            # records.  Every non-cell package part remains untouched.
            for row_number in EXAMPLE_ROWS:
                worksheet_xml = _clear_output_row(
                    worksheet_xml,
                    row_number,
                )
            for offset, record in enumerate(records):
                row_number = self.first_output_row + offset
                worksheet_xml = _apply_authoritative_row_format(
                    worksheet_xml,
                    row_number,
                    authoritative_format,
                )
                worksheet_xml = _write_record(
                    worksheet_xml, row_number, record
                )

            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                dir=output_path.parent,
            )
            os.close(fd)
            temporary_path = Path(temporary_name)
            try:
                with zipfile.ZipFile(temporary_path, "w") as target_zip:
                    for entry in source_zip.infolist():
                        payload = (
                            worksheet_xml
                            if entry.filename == sheet_part
                            else workbook_xml
                            if entry.filename == "xl/workbook.xml"
                            else source_zip.read(entry.filename)
                        )
                        target_zip.writestr(entry, payload)
                os.replace(temporary_path, output_path)
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise

        return output_path


def export_masterdata(
    records: Iterable[MasterDataRecord],
    output_path: str | Path,
    *,
    template_path: str | Path = DEFAULT_TEMPLATE_PATH,
) -> Path:
    """Export already-built records using the default template contract."""

    return MasterDataExcelExporter(template_path).export(records, output_path)


def export_approved_products(
    approved_products: Iterable[Any],
    output_path: str | Path,
    *,
    template_path: str | Path = DEFAULT_TEMPLATE_PATH,
    builder: MasterDataBuilder | None = None,
) -> Path:
    """Build and export approved products in one downstream operation."""

    builder = builder or MasterDataBuilder()
    records = builder.build_many(approved_products)
    return MasterDataExcelExporter(template_path).export(records, output_path)


def _sheet_part_name(
    workbook_zip: zipfile.ZipFile, sheet_name: str
) -> str:
    workbook_xml = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
    relationship_id: str | None = None
    for sheet in workbook_xml.findall(f".//{{{SPREADSHEET_NS}}}sheet"):
        if sheet.get("name") == sheet_name:
            relationship_id = sheet.get(f"{{{DOCUMENT_REL_NS}}}id")
            break
    if relationship_id is None:
        raise ValueError(f"Template sheet {sheet_name!r} was not found")

    relationships = ET.fromstring(
        workbook_zip.read("xl/_rels/workbook.xml.rels")
    )
    target: str | None = None
    for relationship in relationships.findall(
        f".//{{{PACKAGE_REL_NS}}}Relationship"
    ):
        if relationship.get("Id") == relationship_id:
            target = relationship.get("Target")
            break
    if not target:
        raise ValueError(
            f"Worksheet relationship {relationship_id!r} has no target"
        )

    if target.startswith("/"):
        part = PurePosixPath(target.lstrip("/"))
    else:
        part = PurePosixPath("xl") / PurePosixPath(target)
    normalized = str(part)
    if normalized not in workbook_zip.namelist():
        raise ValueError(
            f"Worksheet package part {normalized!r} was not found"
        )
    return normalized


_ROW_APPEARANCE_ATTRIBUTES = (
    "s",
    "customFormat",
    "ht",
    "customHeight",
    "hidden",
    "outlineLevel",
    "collapsed",
    "thickTop",
    "thickBot",
)


def _authoritative_row_format(
    worksheet_xml: bytes,
    row_number: int,
) -> tuple[dict[str, bytes | None], dict[str, bytes | None]]:
    """Read row appearance and A:AB cell-style ids without rewriting XML."""

    row_match = _row_match(worksheet_xml, row_number)
    if row_match is None:
        raise ValueError(
            f"Authoritative template row {row_number} was not found."
        )
    row_xml = row_match.group(0)
    opening_match = re.match(rb"<row\b[^>]*>", row_xml)
    if opening_match is None:
        raise ValueError(
            f"Authoritative template row {row_number} is malformed."
        )
    row_opening = opening_match.group(0)
    row_attributes = {
        name: _xml_attribute(row_opening, name)
        for name in _ROW_APPEARANCE_ATTRIBUTES
    }

    cell_styles: dict[str, bytes | None] = {}
    for column_number in range(1, 29):
        column = _column_name(column_number)
        reference = f"{column}{row_number}"
        cell_match = _cell_match(row_xml, reference)
        if cell_match is None:
            cell_styles[column] = None
            continue
        opening = re.match(rb"<c\b[^>]*?/?>", cell_match.group(0))
        cell_styles[column] = (
            _xml_attribute(opening.group(0), "s")
            if opening is not None
            else None
        )
    return row_attributes, cell_styles


def _apply_authoritative_row_format(
    worksheet_xml: bytes,
    row_number: int,
    authoritative_format: tuple[
        dict[str, bytes | None],
        dict[str, bytes | None],
    ],
) -> bytes:
    """Apply the canonical row-5 appearance while preserving cell payloads.

    Borders, fills, fonts, alignments, number formats and protection are all
    referenced by the cell ``s`` attribute.  Formula bodies, comments,
    validation ranges and extension data are deliberately not copied or
    regenerated.
    """

    row_attributes, cell_styles = authoritative_format
    if _row_match(worksheet_xml, row_number) is None:
        worksheet_xml = _insert_empty_row(worksheet_xml, row_number)

    row_match = _row_match(worksheet_xml, row_number)
    if row_match is None:
        raise ValueError(f"Could not create worksheet row {row_number}.")
    row_xml = row_match.group(0)
    opening_match = re.match(rb"<row\b[^>]*>", row_xml)
    if opening_match is None:
        raise ValueError(f"Worksheet row {row_number} is malformed.")
    updated_opening = opening_match.group(0)
    for name, value in row_attributes.items():
        updated_opening = _set_xml_attribute(updated_opening, name, value)
    updated_row = (
        updated_opening
        + row_xml[opening_match.end() :]
    )
    worksheet_xml = (
        worksheet_xml[: row_match.start()]
        + updated_row
        + worksheet_xml[row_match.end() :]
    )

    for column, style_id in cell_styles.items():
        reference = f"{column}{row_number}"
        if _cell_match(worksheet_xml, reference) is None:
            worksheet_xml = _replace_or_insert_cell(
                worksheet_xml,
                reference,
                b"",
                cell_type=None,
                row_number=row_number,
            )
        cell_match = _cell_match(worksheet_xml, reference)
        if cell_match is None:
            raise ValueError(f"Could not create cell {reference}.")
        cell_xml = cell_match.group(0)
        opening = re.match(rb"<c\b[^>]*?/?>", cell_xml)
        if opening is None:
            raise ValueError(f"Cell {reference} is malformed.")
        updated_cell_opening = _set_xml_attribute(
            opening.group(0),
            "s",
            style_id,
        )
        updated_cell = updated_cell_opening + cell_xml[opening.end() :]
        worksheet_xml = (
            worksheet_xml[: cell_match.start()]
            + updated_cell
            + worksheet_xml[cell_match.end() :]
        )

    return worksheet_xml


def _row_match(xml: bytes, row_number: int) -> re.Match[bytes] | None:
    return re.search(
        rb"<row\b(?=[^>]*\br=[\"']"
        + str(row_number).encode("ascii")
        + rb"[\"'])[^>]*>.*?</row>",
        xml,
        re.DOTALL,
    )


def _cell_match(xml: bytes, reference: str) -> re.Match[bytes] | None:
    reference_bytes = re.escape(reference.encode("ascii"))
    return re.search(
        rb"<c\b(?=[^>]*\br=[\"']"
        + reference_bytes
        + rb"[\"'])[^>]*/>"
        rb"|"
        rb"<c\b(?=[^>]*\br=[\"']"
        + reference_bytes
        + rb"[\"'])[^>]*>.*?</c>",
        xml,
        re.DOTALL,
    )


def _xml_attribute(tag: bytes, name: str) -> bytes | None:
    match = re.search(
        rb"\s+"
        + re.escape(name.encode("ascii"))
        + rb"=(?:\"([^\"]*)\"|'([^']*)')",
        tag,
    )
    if match is None:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def _set_xml_attribute(
    tag: bytes,
    name: str,
    value: bytes | None,
) -> bytes:
    attribute_pattern = re.compile(
        rb"\s+"
        + re.escape(name.encode("ascii"))
        + rb"=(?:\"[^\"]*\"|'[^']*')"
    )
    tag = attribute_pattern.sub(b"", tag)
    if value is None:
        return tag
    close_at = -2 if tag.endswith(b"/>") else -1
    attribute = b" " + name.encode("ascii") + b'="' + value + b'"'
    return tag[:close_at] + attribute + tag[close_at:]


def _column_name(column_number: int) -> str:
    if column_number < 1:
        raise ValueError("column_number must be positive")
    letters = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _write_record(
    worksheet_xml: bytes,
    row_number: int,
    record: MasterDataRecord,
) -> bytes:
    for column, field_name in CELL_FIELDS.items():
        reference = f"{column}{row_number}"
        value = getattr(record, field_name)
        worksheet_xml = _set_cell(
            worksheet_xml,
            reference,
            value,
            row_number=row_number,
        )

    # Keep these columns formula-driven even if a future template row is blank.
    worksheet_xml = _ensure_formula(
        worksheet_xml,
        f"D{row_number}",
        f"LEN(C{row_number})",
        cached_value=_excel_text_length(record.m3_name),
        row_number=row_number,
    )
    worksheet_xml = _ensure_formula(
        worksheet_xml,
        f"F{row_number}",
        f"LEN(E{row_number})",
        cached_value=_excel_text_length(record.m3_description),
        row_number=row_number,
    )
    worksheet_xml = _ensure_formula(
        worksheet_xml,
        f"H{row_number}",
        f"LEN(G{row_number})",
        cached_value=_excel_text_length(record.receipt_text),
        row_number=row_number,
    )
    return worksheet_xml


def _clear_output_row(worksheet_xml: bytes, row_number: int) -> bytes:
    """Clear one template product row while retaining styles and formulas."""

    for column in CELL_FIELDS:
        worksheet_xml = _set_cell(
            worksheet_xml,
            f"{column}{row_number}",
            None,
            row_number=row_number,
        )
    for column, source_column in (("D", "C"), ("F", "E"), ("H", "G")):
        worksheet_xml = _ensure_formula(
            worksheet_xml,
            f"{column}{row_number}",
            f"LEN({source_column}{row_number})",
            cached_value=0,
            row_number=row_number,
        )
    return worksheet_xml


def _ensure_formula(
    worksheet_xml: bytes,
    reference: str,
    formula: str,
    *,
    cached_value: int,
    row_number: int,
) -> bytes:
    """Keep an existing formula group intact or add an explicit formula.

    The production template uses shared formulas over long ranges.  Rewriting a
    single shared master/follower as a normal formula would orphan the rest of
    that group.  Existing formulas are already correct for their row and are
    therefore retained byte-for-byte; only a genuinely blank formula cell gets
    a new explicit formula.
    """

    reference_bytes = re.escape(reference.encode("ascii"))
    cell_pattern = re.compile(
        rb"<c\b(?=[^>]*\br=[\"']"
        + reference_bytes
        + rb"[\"'])[^>]*>.*?</c>",
        re.DOTALL,
    )
    match = cell_pattern.search(worksheet_xml)
    if match is not None and re.search(rb"<f\b", match.group(0)):
        cell_xml = _set_cached_formula_value(
            match.group(0),
            cached_value,
        )
        return (
            worksheet_xml[: match.start()]
            + cell_xml
            + worksheet_xml[match.end() :]
        )
    return _set_formula(
        worksheet_xml,
        reference,
        formula,
        cached_value=cached_value,
        row_number=row_number,
    )


def _excel_text_length(value: Any) -> int:
    """Return the cached LEN result for the text written by this exporter."""

    return 0 if value is None else len(str(value))


def _set_cached_formula_value(cell_xml: bytes, value: int) -> bytes:
    cached = f"<v>{value}</v>".encode("ascii")
    value_pattern = re.compile(rb"<v\b[^>]*>.*?</v>", re.DOTALL)
    if value_pattern.search(cell_xml):
        return value_pattern.sub(cached, cell_xml, count=1)
    closing = cell_xml.rfind(b"</c>")
    if closing < 0:
        raise ValueError("Formula cell is malformed")
    return cell_xml[:closing] + cached + cell_xml[closing:]


def _set_cell(
    xml: bytes,
    reference: str,
    value: str | None,
    *,
    row_number: int,
) -> bytes:
    body = b"" if value is None else _inline_string_body(value)
    return _replace_or_insert_cell(
        xml,
        reference,
        body,
        cell_type=None if value is None else "inlineStr",
        row_number=row_number,
    )


def _set_formula(
    xml: bytes,
    reference: str,
    formula: str,
    *,
    cached_value: int,
    row_number: int,
) -> bytes:
    body = (
        f"<f>{escape(formula)}</f><v>{cached_value}</v>".encode("utf-8")
    )
    return _replace_or_insert_cell(
        xml,
        reference,
        body,
        cell_type=None,
        row_number=row_number,
    )


def _normalize_calculation_properties(workbook_xml: bytes) -> bytes:
    """Request automatic/full recalculation while retaining the template calcId."""

    pattern = re.compile(
        rb"<calcPr\b[^>]*/>|<calcPr\b[^>]*>.*?</calcPr>",
        re.DOTALL,
    )
    match = pattern.search(workbook_xml)
    if match is None:
        calculation = (
            b'<calcPr calcMode="auto" fullCalcOnLoad="1" '
            b'forceFullCalc="1"/>'
        )
        insertion = workbook_xml.rfind(b"</workbook>")
        if insertion < 0:
            raise ValueError("Workbook package part is malformed")
        return (
            workbook_xml[:insertion]
            + calculation
            + workbook_xml[insertion:]
        )

    element = match.group(0)
    opening_match = re.match(rb"<calcPr\b[^>]*?/?>", element)
    if opening_match is None:
        raise ValueError("Workbook calculation properties are malformed")
    opening = opening_match.group(0)
    for name, value in (
        ("calcMode", b"auto"),
        ("fullCalcOnLoad", b"1"),
        ("forceFullCalc", b"1"),
    ):
        opening = _set_xml_attribute(opening, name, value)
    updated = opening + element[opening_match.end() :]
    return workbook_xml[: match.start()] + updated + workbook_xml[match.end() :]


def _inline_string_body(value: str) -> bytes:
    text = str(value)
    space = ' xml:space="preserve"' if text != text.strip() else ""
    return (
        f"<is><t{space}>{escape(text)}</t></is>".encode("utf-8")
    )


def _replace_or_insert_cell(
    xml: bytes,
    reference: str,
    body: bytes,
    *,
    cell_type: str | None,
    row_number: int,
) -> bytes:
    reference_bytes = re.escape(reference.encode("ascii"))
    cell_pattern = re.compile(
        rb"<c\b"
        rb"(?=[^>]*\br=[\"']"
        + reference_bytes
        + rb"[\"'])"
        rb"[^>]*/>"
        rb"|"
        rb"<c\b"
        rb"(?=[^>]*\br=[\"']"
        + reference_bytes
        + rb"[\"'])"
        rb"[^>]*>.*?</c>",
        re.DOTALL,
    )
    match = cell_pattern.search(xml)
    if match is not None:
        original_cell = match.group(0)
        opening_match = re.match(
            rb"<c\b([^>/]*)(?:/?>)",
            original_cell,
        )
        if opening_match is None:
            raise ValueError(
                f"Could not read attributes for cell {reference}."
            )
        attributes = opening_match.group(1).rstrip()
        # Preserve all template attributes, especially the style ``s`` value;
        # replace only the cell data type.
        attributes = re.sub(
            rb"\s+t=(?:\"[^\"]*\"|'[^']*')",
            b"",
            attributes,
        )
        if cell_type is not None:
            attributes += f' t="{cell_type}"'.encode("ascii")
        replacement = b"<c" + attributes + b">" + body + b"</c>"
        return xml[: match.start()] + replacement + xml[match.end() :]

    row_pattern = re.compile(
        rb"<row\b(?=[^>]*\br=[\"']"
        + str(row_number).encode("ascii")
        + rb"[\"'])[^>]*>.*?</row>",
        re.DOTALL,
    )
    row_match = row_pattern.search(xml)
    if row_match is None:
        xml = _insert_empty_row(xml, row_number)
        return _replace_or_insert_cell(
            xml,
            reference,
            body,
            cell_type=cell_type,
            row_number=row_number,
        )

    type_attribute = (
        b"" if cell_type is None else f' t="{cell_type}"'.encode("ascii")
    )
    new_cell = (
        f'<c r="{reference}"'.encode("ascii")
        + type_attribute
        + b">"
        + body
        + b"</c>"
    )
    row_xml = row_match.group(0)
    insert_at = _cell_insert_position(row_xml, reference)
    updated_row = row_xml[:insert_at] + new_cell + row_xml[insert_at:]
    return xml[: row_match.start()] + updated_row + xml[row_match.end() :]


def _cell_insert_position(row_xml: bytes, reference: str) -> int:
    target_column = _column_number(reference)
    for match in re.finditer(
        rb"<c\b(?=[^>]*\br=[\"']([A-Z]+)\d+[\"'])[^>]*/>"
        rb"|"
        rb"<c\b(?=[^>]*\br=[\"']([A-Z]+)\d+[\"'])[^>]*>.*?</c>",
        row_xml,
        re.DOTALL,
    ):
        cell_reference_match = re.search(
            rb"\br=[\"']([A-Z]+)\d+[\"']", match.group(0)
        )
        if (
            cell_reference_match is not None
            and _column_number(cell_reference_match.group(1).decode("ascii"))
            > target_column
        ):
            return match.start()
    closing = row_xml.rfind(b"</row>")
    if closing < 0:
        raise ValueError("Malformed worksheet row")
    return closing


def _column_number(reference_or_column: str) -> int:
    letters_match = re.match(r"([A-Z]+)", reference_or_column.upper())
    if letters_match is None:
        raise ValueError(f"Invalid cell reference: {reference_or_column!r}")
    number = 0
    for character in letters_match.group(1):
        number = number * 26 + ord(character) - ord("A") + 1
    return number


def _insert_empty_row(xml: bytes, row_number: int) -> bytes:
    sheet_data_end = xml.find(b"</sheetData>")
    if sheet_data_end < 0:
        raise ValueError("Template worksheet has no sheetData element")
    row = f'<row r="{row_number}"></row>'.encode("ascii")
    return xml[:sheet_data_end] + row + xml[sheet_data_end:]
