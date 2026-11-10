from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from app.models import SourceProduct


FIELD_ALIASES = {
    "saether_code": {
        "sæther code",
        "saether code",
    },
    "product_type": {
        "product type",
    },
    "product_code": {
        "product code",
        "supplier item no.",
        "supplier item no",
    },
    "ean": {
        "ean",
        "ea gtin (ean)",
        "gtin",
    },
    "product_name": {
        "product name",
        "item description",
        "description",
    },
    "brand_name": {
        "brand",
        "brand name",
    },
}


PLACEHOLDERS = {
    "",
    "0",
    "none",
    "nan",
    "n/a",
    "suppliers ref no.",
    "gtin/ean on item",
    "master brand",
    "item name/description",
}


def normalize_header(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(
        str(value)
        .replace("\n", " ")
        .strip()
        .casefold()
        .split()
    )


def identify_field(value: Any) -> str | None:
    header = normalize_header(value)

    for field_name, aliases in FIELD_ALIASES.items():
        if header in aliases:
            return field_name

    return None


def clean_cell(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, float) and value.is_integer():
        value = int(value)

    cleaned = str(value).strip()

    if not cleaned:
        return None

    if cleaned.casefold() in PLACEHOLDERS:
        return None

    return cleaned


def clean_ean(value: Any) -> str | None:
    value = clean_cell(value)

    if not value:
        return None

    value = value.replace(" ", "")

    if not value.isdigit():
        return None

    if not 8 <= len(value) <= 14:
        return None

    return value


def find_header_row(
    worksheet,
    max_rows: int = 50,
) -> tuple[int | None, dict[str, int]]:
    for row_number in range(
        1,
        min(worksheet.max_row, max_rows) + 1,
    ):
        fields: dict[str, int] = {}

        for column_number in range(
            1,
            worksheet.max_column + 1,
        ):
            value = worksheet.cell(
                row=row_number,
                column=column_number,
            ).value

            field_name = identify_field(value)

            if field_name:
                fields[field_name] = column_number

        has_identifier = (
            "product_code" in fields
            or "ean" in fields
        )

        if has_identifier and "product_name" in fields:
            return row_number, fields

    return None, {}


def read_products_from_sheet(
    worksheet,
    source_file: str,
) -> list[SourceProduct]:
    header_row, fields = find_header_row(worksheet)

    if header_row is None:
        return []

    products: list[SourceProduct] = []

    for row_number in range(
        header_row + 1,
        worksheet.max_row + 1,
    ):
        saether_code = None
        product_type = None
        product_code = None
        ean = None
        product_name = None
        brand_name = None

        if "saether_code" in fields:
            saether_code = clean_cell(
                worksheet.cell(
                    row=row_number,
                    column=fields["saether_code"],
                ).value
            )

        if "product_type" in fields:
            product_type = clean_cell(
                worksheet.cell(
                    row=row_number,
                    column=fields["product_type"],
                ).value
            )

        if "product_code" in fields:
            product_code = clean_cell(
                worksheet.cell(
                    row=row_number,
                    column=fields["product_code"],
                ).value
            )

        if "ean" in fields:
            ean = clean_ean(
                worksheet.cell(
                    row=row_number,
                    column=fields["ean"],
                ).value
            )

        if "product_name" in fields:
            product_name = clean_cell(
                worksheet.cell(
                    row=row_number,
                    column=fields["product_name"],
                ).value
            )

        if "brand_name" in fields:
            brand_name = clean_cell(
                worksheet.cell(
                    row=row_number,
                    column=fields["brand_name"],
                ).value
            )

        # En produktsrække skal som minimum have et navn.
        if not product_name:
            continue

        # Og mindst én reel identifikator.
        if not product_code and not ean:
            continue

        raw_data = {
            "_source_sheet": worksheet.title,
            "_source_row": row_number,
        }

        products.append(
            SourceProduct(
                product_code=product_code,
                ean=ean,
                product_name=product_name,
                brand_name=brand_name,
                saether_code=saether_code,
                product_type=product_type,
                source_file=source_file,
                raw_data=raw_data,
            )
        )

    return products


def read_excel(path) -> list[SourceProduct]:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(
            f"Excel-filen blev ikke fundet: {path}"
        )

    workbook = load_workbook(
        path,
        read_only=True,
        data_only=True,
    )

    products: list[SourceProduct] = []

    try:
        for worksheet in workbook.worksheets:
            products.extend(
                read_products_from_sheet(
                    worksheet=worksheet,
                    source_file=path.name,
                )
            )

    finally:
        workbook.close()

    return products