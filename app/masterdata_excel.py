"""Lossless writer for the Sæther MASTERDATA Excel template.

Only cell payloads in ``Master template`` are changed.  The XLSX package is
otherwise copied entry-for-entry, which preserves all sheets, example rows,
styles, formulas, data validations, extension lists and other template parts.
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
MASTER_SHEET_NAME = "Master template"
FIRST_OUTPUT_ROW = 7

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
        sheet_name: str = MASTER_SHEET_NAME,
        first_output_row: int = FIRST_OUTPUT_ROW,
    ) -> None:
        self.template_path = Path(template_path)
        self.sheet_name = sheet_name
        self.first_output_row = first_output_row

    def export(
        self,
        records: Iterable[MasterDataRecord],
        output_path: str | Path,
    ) -> Path:
        records = list(records)
        if not records:
            raise ValueError("At least one MasterDataRecord is required")
        if self.first_output_row < FIRST_OUTPUT_ROW:
            raise ValueError(
                "first_output_row must be 7 or later so example rows 5 and 6 remain unchanged"
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
            for offset, record in enumerate(records):
                row_number = self.first_output_row + offset
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
    worksheet_xml = _set_formula(
        worksheet_xml,
        f"D{row_number}",
        f"LEN(C{row_number})",
        row_number=row_number,
    )
    worksheet_xml = _set_formula(
        worksheet_xml,
        f"F{row_number}",
        f"LEN(E{row_number})",
        row_number=row_number,
    )
    worksheet_xml = _set_formula(
        worksheet_xml,
        f"H{row_number}",
        f"LEN(G{row_number})",
        row_number=row_number,
    )
    return worksheet_xml


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
    row_number: int,
) -> bytes:
    body = f"<f>{escape(formula)}</f>".encode("utf-8")
    return _replace_or_insert_cell(
        xml,
        reference,
        body,
        cell_type=None,
        row_number=row_number,
    )


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
    reference_bytes = re.escape(
        reference.encode("ascii")
    )

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
                f"Kunne ikke læse attributter for celle "
                f"{reference}."
            )

        attributes = opening_match.group(1).rstrip()

        # Bevar alle øvrige eksisterende attributter,
        # herunder style-attributten s="...".
        # Fjern kun en eventuel datatype.
        attributes = re.sub(
            rb"\s+t=(?:\"[^\"]*\"|'[^']*')",
            b"",
            attributes,
        )

        if cell_type is not None:
            attributes += (
                f' t="{cell_type}"'.encode("ascii")
            )

        replacement = (
            b"<c"
            + attributes
            + b">"
            + body
            + b"</c>"
        )

        return (
            xml[:match.start()]
            + replacement
            + xml[match.end():]
        )

    row_pattern = re.compile(
        rb"<row\b(?=[^>]*\br=[\"']"
        + str(row_number).encode("ascii")
        + rb"[\"'])[^>]*>.*?</row>",
        re.DOTALL,
    )

    row_match = row_pattern.search(xml)

    if row_match is None:
        xml = _insert_empty_row(
            xml,
            row_number,
        )

        return _replace_or_insert_cell(
            xml,
            reference,
            body,
            cell_type=cell_type,
            row_number=row_number,
        )

    type_attribute = (
        b""
        if cell_type is None
        else f' t="{cell_type}"'.encode("ascii")
    )

    new_cell = (
        f'<c r="{reference}"'.encode("ascii")
        + type_attribute
        + b">"
        + body
        + b"</c>"
    )

    row_xml = row_match.group(0)

    insert_at = _cell_insert_position(
        row_xml,
        reference,
    )

    updated_row = (
        row_xml[:insert_at]
        + new_cell
        + row_xml[insert_at:]
    )

    return (
        xml[:row_match.start()]
        + updated_row
        + xml[row_match.end():]
    )

def _cell_insert_position(row_xml: bytes, reference: str) -> int:
    target_column = _column_number(reference)
    for match in re.finditer(
        rb"<c\b(?=[^>]*\br=[\"']([A-Z]+)\d+[\"'])[^>]*(?:/>|>.*?</c>)",
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
