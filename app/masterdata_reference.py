"""Read classification reference values from the current MASTERDATA template.

The workbook remains the source of truth.  This module reads the XLSX package
without rewriting it and exposes only the reference data required by the
MASTERDATA builder.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable
from xml.etree import ElementTree as ET
import zipfile


SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOCUMENT_REL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS = f"{{{SPREADSHEET_NS}}}"


@dataclass(frozen=True, slots=True)
class ProductLineReference:
    base_code: str
    description: str

    @property
    def export_code(self) -> str:
        """Return the template-defined export value.

        The current template lists special product lines as a base AGr value
        whose description contains ``spec. products`` while the examples use an
        ``S`` suffix.  The suffix is therefore derived from the template row,
        not from a brand-specific rule.
        """

        normalized = self.description.casefold()
        if "spec" in normalized and "product" in normalized:
            return (
                self.base_code
                if self.base_code.casefold().endswith("s")
                else f"{self.base_code}S"
            )
        return self.base_code


@dataclass(frozen=True, slots=True)
class ItemCategoryReference:
    code: str
    description: str
    combined: str


@dataclass(frozen=True, slots=True)
class TemplateReferenceData:
    product_lines: tuple[ProductLineReference, ...] = ()
    item_categories: tuple[ItemCategoryReference, ...] = ()

    def product_line_option_payload(self) -> list[dict[str, str]]:
        """Return stable, non-empty option objects for the React override UI.

        ``value`` is the exact value accepted by review validation and written
        to MASTERDATA.  ``label`` keeps the workbook description visible to the
        reviewer.  De-duplication is value based and preserves workbook order.
        """

        options: list[dict[str, str]] = []
        seen: set[str] = set()
        for reference in self.product_lines:
            value = _clean(reference.export_code)
            if value is None or value in seen:
                continue
            seen.add(value)
            description = _clean(reference.description)
            options.append(
                {
                    "value": value,
                    "label": (
                        f"{value} — {description}"
                        if description and description != value
                        else value
                    ),
                }
            )
        return options

    def item_category_option_payload(self) -> list[dict[str, str]]:
        """Return selectable combined values from ``Data for drop downs``."""

        options: list[dict[str, str]] = []
        seen: set[str] = set()
        for reference in self.item_categories:
            value = _clean(reference.combined)
            if value is None:
                code = _clean(reference.code)
                description = _clean(reference.description)
                if code and description:
                    value = f"{code} {description}"
            if value is None or value in seen:
                continue
            seen.add(value)
            options.append({"value": value, "label": value})
        return options

    @classmethod
    def from_xlsx(cls, path: str | Path) -> "TemplateReferenceData":
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"MASTERDATA template was not found: {path}")

        with zipfile.ZipFile(path, "r") as workbook_zip:
            shared_strings = _shared_strings(workbook_zip)
            product_line_rows = _sheet_rows(
                workbook_zip,
                "Product line",
                shared_strings,
            )
            category_rows = _sheet_rows(
                workbook_zip,
                "Data for drop downs",
                shared_strings,
            )

        product_lines: list[ProductLineReference] = []
        for row in product_line_rows:
            code = _clean(row.get("A"))
            description = _clean(row.get("B"))
            if code is None or description is None:
                continue
            if code.casefold() in {"agr", "code"}:
                continue
            product_lines.append(ProductLineReference(code, description))

        item_categories: list[ItemCategoryReference] = []
        for row in category_rows:
            code = _clean(row.get("A"))
            description = _clean(row.get("B"))
            combined = _clean(row.get("C"))
            if code is None or description is None:
                continue
            if code.casefold() in {"item category", "code"}:
                continue
            item_categories.append(
                ItemCategoryReference(
                    code=code,
                    description=description,
                    combined=combined or f"{code} {description}",
                )
            )

        return cls(tuple(product_lines), tuple(item_categories))

    def item_category(self, code: object) -> ItemCategoryReference | None:
        normalized = _identifier(code)
        if normalized is None:
            return None
        matches = [
            reference
            for reference in self.item_categories
            if _identifier(reference.code) == normalized
        ]
        return matches[0] if len(matches) == 1 else None

    def product_line_for_brand(
        self,
        brand_code: object,
        brand_name: object,
    ) -> ProductLineReference | None:
        """Resolve one template row using both MMBUAR and MMBUARTX40.

        Code identity is mandatory.  Brand-name evidence must also overlap the
        description so an unrelated row with the same textual code cannot be
        selected silently.
        """

        code = _identifier(brand_code)
        name_tokens = _tokens(brand_name)
        if code is None or not name_tokens:
            return None

        candidates = [
            reference
            for reference in self.product_lines
            if _identifier(reference.base_code) == code
            and name_tokens.intersection(_tokens(reference.description))
        ]
        return candidates[0] if len(candidates) == 1 else None


def _shared_strings(workbook_zip: zipfile.ZipFile) -> tuple[str, ...]:
    if "xl/sharedStrings.xml" not in workbook_zip.namelist():
        return ()
    root = ET.fromstring(workbook_zip.read("xl/sharedStrings.xml"))
    return tuple(
        "".join(text.text or "" for text in item.iter(f"{_NS}t"))
        for item in root.findall(f"{_NS}si")
    )


def _sheet_rows(
    workbook_zip: zipfile.ZipFile,
    sheet_name: str,
    shared_strings: tuple[str, ...],
) -> list[dict[str, str]]:
    part_name = _sheet_part_name(workbook_zip, sheet_name)
    root = ET.fromstring(workbook_zip.read(part_name))
    rows: list[dict[str, str]] = []
    for row in root.findall(f".//{_NS}row"):
        values: dict[str, str] = {}
        for cell in row.findall(f"{_NS}c"):
            reference = cell.get("r", "")
            column = "".join(character for character in reference if character.isalpha())
            if not column:
                continue
            value = _cell_value(cell, shared_strings)
            if value is not None:
                values[column] = value
        if values:
            rows.append(values)
    return rows


def _cell_value(cell: ET.Element, shared_strings: tuple[str, ...]) -> str | None:
    inline = cell.find(f"{_NS}is")
    if inline is not None:
        return "".join(text.text or "" for text in inline.iter(f"{_NS}t"))

    value = cell.find(f"{_NS}v")
    if value is None or value.text is None:
        return None
    raw = value.text
    if cell.get("t") == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError):
            return None
    return raw


def _sheet_part_name(workbook_zip: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
    relationship_id: str | None = None
    for sheet in workbook.findall(f".//{_NS}sheet"):
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
        raise ValueError(f"Template sheet {sheet_name!r} has no package target")

    part = (
        PurePosixPath(target.lstrip("/"))
        if target.startswith("/")
        else PurePosixPath("xl") / PurePosixPath(target)
    )
    normalized = str(part)
    if normalized not in workbook_zip.namelist():
        raise ValueError(f"Template package part {normalized!r} was not found")
    return normalized


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _identifier(value: object) -> str | None:
    text = _clean(value)
    if text is None:
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text.casefold()


def _tokens(value: object) -> set[str]:
    text = _clean(value)
    if text is None:
        return set()
    return {
        token
        for token in "".join(
            character if character.isalnum() else " "
            for character in text.casefold()
        ).split()
        if len(token) >= 2 and token not in {"spec", "products", "product"}
    }
