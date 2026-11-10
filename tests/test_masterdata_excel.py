from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill

from app.masterdata_excel import MasterDataExcelExporter
from app.masterdata_model import MasterDataRecord


EXPECTED_SHEETS = [
    "Master template",
    "Product line",
    "Data for drop downs",
    "Kategorioversigt",
    "Link til guide",
]


@pytest.fixture
def template_path(tmp_path: Path) -> Path:
    path = tmp_path / "saether_masterdata_template.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Master template"
    for name in EXPECTED_SHEETS[1:]:
        workbook.create_sheet(name)

    headers = [
        "Copy from item number",
        "New item number",
        "Line 1: All UPPERCASE LETTERS (max 30 characters)",
        "Length",
        "Line 2: Description as stated on the product",
        "Length",
        "Text for the till receipt",
        "Length",
        "Item type",
        "Item group (M3 Varegruppe)",
        "Item group description (max 40 characters)",
        "Product group",
        "Product line",
        "Item category",
        "REF no.",
        "EAN / GTIN",
        "Udgave NY/OS",
        "Net content",
        "ML/GR/STK",
        "Delivery week",
        "Supplier no. for POS",
        "Gender",
        "Distribution channel (CLARINS)",
        "COGS",
        "RRP DKK",
        "RRP SEK",
        "RRP NOK",
        "RRP EUR",
    ]
    for column, value in enumerate(headers, 1):
        sheet.cell(4, column, value)

    example_5 = [
        "EXAMPLE",
        None,
        "FEB HELLA THICC VOL MAS BROWN",
        "=LEN(C5)",
        "Brown",
        "=LEN(E5)",
        "FEB HELLA MASC BROWN",
        "=LEN(G5)",
        "00",
        "348365",
        "Hella Thicc Volumizing Mascara",
        "34802",
        "348S",
        "75 Mascara",
        "76021",
        "5799999999999",
        "NY",
    ]
    example_6 = [
        "EXAMPLE",
        None,
        "MK POUR FEMME EDP 100ML",
        "=LEN(C6)",
        "Eau de parfum natural spray",
        "=LEN(E6)",
        "MK POUR FEM 100ML",
        "=LEN(G6)",
        "00",
        "103028",
        None,
        "10301",
        "103S",
        "02 Edp",
        "450432",
        "850049716321",
        "NY",
    ]
    for row_number, values in ((5, example_5), (6, example_6)):
        for column, value in enumerate(values, 1):
            sheet.cell(row_number, column, value)

    fill = PatternFill("solid", fgColor="D9EAD3")
    for row in range(7, 10):
        for column in range(1, 29):
            cell = sheet.cell(row, column)
            cell.fill = fill
            cell.font = Font(name="Arial", size=10)
        sheet[f"D{row}"] = f"=LEN(C{row})"
        sheet[f"F{row}"] = f"=LEN(E{row})"
        sheet[f"H{row}"] = f"=LEN(G{row})"

    workbook["Product line"]["A1"] = "AGr"
    workbook["Data for drop downs"]["A1"] = "Item category"
    workbook["Kategorioversigt"]["A2"] = "Category 1 - KEYS"
    workbook["Link til guide"]["A1"] = "N:\\Nordic_Datasharing\\guide.pdf"
    workbook.save(path)
    return path


@pytest.fixture
def record() -> MasterDataRecord:
    return MasterDataRecord(
        item_number="12819220316",
        m3_name="TEST SI INSTANT SMOOTH 15ML",
        item_type="12",
        item_group="128591",
        item_group_description="Instant Smooth",
        product_group="12804",
        product_line="740",
        ref_number="80133626",
        ean="3666057504815",
        edition="NY",
    )


def test_reopens_generated_workbook_and_verifies_row_7_mapping(
    template_path: Path,
    record: MasterDataRecord,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "MASTERDATA_80133626.xlsx"

    MasterDataExcelExporter(template_path).export([record], output_path)

    workbook = load_workbook(output_path, data_only=False)
    sheet = workbook["Master template"]
    assert sheet["B7"].value == "12819220316"
    assert sheet["C7"].value == "TEST SI INSTANT SMOOTH 15ML"
    assert sheet["D7"].value == "=LEN(C7)"
    assert sheet["I7"].value == "12"
    assert sheet["J7"].value == "128591"
    assert sheet["K7"].value == "Instant Smooth"
    assert sheet["L7"].value == "12804"
    assert sheet["M7"].value == "740"
    assert sheet["O7"].value == "80133626"
    assert sheet["P7"].value == "3666057504815"
    assert sheet["Q7"].value == "NY"


def test_preserves_example_rows_sheets_formulas_and_formatting(
    template_path: Path,
    record: MasterDataRecord,
    tmp_path: Path,
) -> None:
    before = load_workbook(template_path, data_only=False)
    before_sheet = before["Master template"]
    example_rows_before = [
        tuple(before_sheet.cell(row, column).value for column in range(1, 29))
        for row in (5, 6)
    ]
    style_before = before_sheet["B7"].style_id

    output_path = tmp_path / "MASTERDATA.xlsx"
    MasterDataExcelExporter(template_path).export([record], output_path)

    after = load_workbook(output_path, data_only=False)
    after_sheet = after["Master template"]
    assert after.sheetnames == EXPECTED_SHEETS
    assert [
        tuple(after_sheet.cell(row, column).value for column in range(1, 29))
        for row in (5, 6)
    ] == example_rows_before
    assert after_sheet["B7"].style_id == style_before
    assert after_sheet["F7"].value == "=LEN(E7)"
    assert after_sheet["H7"].value == "=LEN(G7)"


def test_leaves_undocumented_fields_blank(
    template_path: Path,
    record: MasterDataRecord,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "MASTERDATA.xlsx"
    MasterDataExcelExporter(template_path).export([record], output_path)

    sheet = load_workbook(output_path, data_only=False)["Master template"]
    for reference in (
        "A7",
        "E7",
        "G7",
        "N7",
        "R7",
        "S7",
        "T7",
        "U7",
        "V7",
        "W7",
        "X7",
        "Y7",
        "Z7",
        "AA7",
        "AB7",
    ):
        assert sheet[reference].value is None


def test_writes_multiple_products_from_row_7_without_inserting_rows(
    template_path: Path,
    record: MasterDataRecord,
    tmp_path: Path,
) -> None:
    second = MasterDataRecord(
        item_number="12819220317",
        m3_name="SECOND PRODUCT",
        item_type="12",
        ref_number="80133627",
        ean="3666057504822",
    )
    output_path = tmp_path / "MASTERDATA.xlsx"

    MasterDataExcelExporter(template_path).export(
        [record, second], output_path
    )

    sheet = load_workbook(output_path, data_only=False)["Master template"]
    assert sheet["B7"].value == "12819220316"
    assert sheet["B8"].value == "12819220317"
    assert sheet["D8"].value == "=LEN(C8)"
    assert sheet["A5"].value == "EXAMPLE"
    assert sheet["A6"].value == "EXAMPLE"


def test_only_target_worksheet_part_changes(
    template_path: Path,
    record: MasterDataRecord,
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "MASTERDATA.xlsx"
    MasterDataExcelExporter(template_path).export([record], output_path)

    with ZipFile(template_path) as before_zip, ZipFile(output_path) as after_zip:
        assert before_zip.namelist() == after_zip.namelist()
        changed = {
            name
            for name in before_zip.namelist()
            if before_zip.read(name) != after_zip.read(name)
        }
    assert changed == {"xl/worksheets/sheet1.xml"}
