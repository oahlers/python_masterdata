from __future__ import annotations

from pathlib import Path
import re
from zipfile import ZipFile

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

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

    example_rows = {
        5: ["EXAMPLE", None, "FEB HELLA THICC VOL MAS BROWN", "=LEN(C5)", "Brown", "=LEN(E5)", "FEB HELLA MASC BROWN", "=LEN(G5)", "00", "348365", "Hella Thicc Volumizing Mascara", "34802", "348S", "75 Mascara"],
        6: ["EXAMPLE", None, "MK POUR FEMME EDP 100ML", "=LEN(C6)", "Eau de parfum natural spray", "=LEN(E6)", "MK POUR FEM 100ML", "=LEN(G6)", "00", "103028", None, "10301", "103S", "02 Edp"],
    }
    for row, values in example_rows.items():
        for column, value in enumerate(values, 1):
            sheet.cell(row, column, value)

    authoritative_fill = PatternFill("solid", fgColor="D9EAD3")
    authoritative_border = Border(
        left=Side(style="thin", color="000000"),
        right=Side(style="thin", color="000000"),
        top=Side(style="thin", color="000000"),
        bottom=Side(style="thin", color="000000"),
    )
    for row in range(5, 14):
        for column in range(1, 29):
            cell = sheet.cell(row, column)
            if row <= 6:
                cell.fill = authoritative_fill
                cell.font = Font(name="Arial", size=10)
                cell.border = authoritative_border
                cell.alignment = Alignment(
                    horizontal="center" if column != 3 else "left",
                    vertical="center",
                )
                cell.number_format = "0" if column in {1, 2, 12, 13, 14} else "General"
            else:
                # Deliberately model the real acceptance regression: later
                # rows have valid formulas but a visibly different base style.
                cell.fill = PatternFill(fill_type=None)
                cell.font = Font(name="Calibri", size=11, italic=True)
                cell.border = Border()
                cell.alignment = Alignment()
                cell.number_format = "General"
        sheet[f"D{row}"] = f"=LEN(C{row})"
        sheet[f"F{row}"] = f"=LEN(E{row})"
        sheet[f"H{row}"] = f"=LEN(G{row})"

    sheet["A4"].comment = Comment("Header guidance", "Masterdata")
    item_type_validation = DataValidation(
        type="list",
        formula1="'Data for drop downs'!$E$2:$E$20",
    )
    item_type_validation.add("I5:I13")
    sheet.add_data_validation(item_type_validation)
    name_validation = DataValidation(
        type="textLength",
        operator="lessThanOrEqual",
        formula1="30",
    )
    name_validation.add("C5:C13")
    sheet.add_data_validation(name_validation)
    workbook.save(path)
    return path


@pytest.fixture
def record() -> MasterDataRecord:
    return MasterDataRecord(
        item_number="12819220316",
        m3_name="TEST SI INSTANT SMOOTH 15ML",
        m3_description="Instant Smooth perfecting touch",
        receipt_text=None,
        item_type="12",
        item_group="128591",
        item_group_description=None,
        product_group="12804",
        product_line="128S",
        item_category="740 MKU face primer",
        ref_number="80133626",
        ean="3666057504815",
    )


def test_writes_documented_semantics_to_c_e_g_m_n(
    template_path: Path,
    record: MasterDataRecord,
    tmp_path: Path,
) -> None:
    output = tmp_path / "MASTERDATA.xlsx"
    MasterDataExcelExporter(
        template_path,
        reference_template_path=template_path,
    ).export([record], output)
    sheet = load_workbook(output, data_only=False)["Master template"]
    assert sheet["C5"].value == record.m3_name
    assert sheet["E5"].value == record.m3_description
    assert sheet["G5"].value is None
    assert sheet["M5"].value == record.product_line
    assert sheet["N5"].value == record.item_category
    assert sheet["K5"].value is None
    assert sheet["D5"].value == "=LEN(C5)"
    assert sheet["F5"].value == "=LEN(E5)"
    assert sheet["H5"].value == "=LEN(G5)"


def test_formula_cached_values_match_generated_text(
    template_path: Path,
    record: MasterDataRecord,
    tmp_path: Path,
) -> None:
    output = tmp_path / "MASTERDATA.xlsx"
    MasterDataExcelExporter(
        template_path,
        reference_template_path=template_path,
    ).export([record], output)

    cached = load_workbook(output, data_only=True)["Master template"]
    assert cached["D5"].value == len(record.m3_name or "")
    assert cached["F5"].value == len(record.m3_description or "")
    assert cached["H5"].value == 0
    assert cached["D6"].value in (None, 0)
    assert cached["F6"].value in (None, 0)
    assert cached["H6"].value in (None, 0)


def test_export_requests_automatic_full_recalculation(
    template_path: Path,
    record: MasterDataRecord,
    tmp_path: Path,
) -> None:
    output = tmp_path / "MASTERDATA.xlsx"
    MasterDataExcelExporter(
        template_path,
        reference_template_path=template_path,
    ).export([record], output)

    with ZipFile(output) as package:
        workbook_xml = package.read("xl/workbook.xml")
    calc_pr = re.search(rb"<calcPr\b[^>]*/?>", workbook_xml)
    assert calc_pr is not None
    assert b'calcMode="auto"' in calc_pr.group(0)
    assert b'fullCalcOnLoad="1"' in calc_pr.group(0)
    assert b'forceFullCalc="1"' in calc_pr.group(0)


def test_rejects_export_record_without_item_number(
    template_path: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "MASTERDATA.xlsx"
    preview_only_record = MasterDataRecord(
        item_number=None,
        m3_name="PREVIEW ONLY",
    )

    with pytest.raises(
        ValueError,
        match="item_number is required for MASTERDATA export",
    ):
        MasterDataExcelExporter(
            template_path,
            reference_template_path=template_path,
        ).export([preview_only_record], output)

    assert not output.exists()


def test_clears_examples_in_output_but_preserves_source_sheets_and_styles(
    template_path: Path,
    record: MasterDataRecord,
    tmp_path: Path,
) -> None:
    before = load_workbook(template_path, data_only=False)
    before_values = [tuple(before["Master template"].cell(row, column).value for column in range(1, 29)) for row in (5, 6)]
    style_before = before["Master template"]["B5"].style_id
    output = tmp_path / "MASTERDATA.xlsx"
    MasterDataExcelExporter(
        template_path,
        reference_template_path=template_path,
    ).export([record], output)
    after = load_workbook(output, data_only=False)
    assert after.sheetnames == EXPECTED_SHEETS
    assert before_values[0][0] == "EXAMPLE"
    assert before_values[1][0] == "EXAMPLE"
    assert after["Master template"]["A5"].value is None
    assert after["Master template"]["A6"].value is None
    assert after["Master template"]["B5"].style_id == style_before
    original_again = load_workbook(template_path, data_only=False)
    assert original_again["Master template"]["A5"].value == "EXAMPLE"
    assert original_again["Master template"]["A6"].value == "EXAMPLE"


def test_writes_multiple_rows_without_inserting_template_rows(
    template_path: Path,
    record: MasterDataRecord,
    tmp_path: Path,
) -> None:
    second = MasterDataRecord(item_number="12819220317", m3_name="SECOND PRODUCT")
    output = tmp_path / "MASTERDATA.xlsx"
    MasterDataExcelExporter(
        template_path,
        reference_template_path=template_path,
    ).export([record, second], output)
    sheet = load_workbook(output, data_only=False)["Master template"]
    assert sheet["B5"].value == record.item_number
    assert sheet["B6"].value == second.item_number
    assert sheet["A5"].value is None
    assert sheet["A6"].value is None


def test_one_record_leaves_row_6_clean_with_formulas(
    template_path: Path,
    record: MasterDataRecord,
    tmp_path: Path,
) -> None:
    output = tmp_path / "MASTERDATA.xlsx"
    MasterDataExcelExporter(
        template_path,
        reference_template_path=template_path,
    ).export([record], output)
    sheet = load_workbook(output, data_only=False)["Master template"]
    assert all(sheet.cell(6, column).value is None for column in (1, 2, 3, 5, 7, 9, 10, 11, 12, 13, 14))
    assert sheet["D6"].value == "=LEN(C6)"
    assert sheet["F6"].value == "=LEN(E6)"
    assert sheet["H6"].value == "=LEN(G6)"


def test_nine_records_fill_rows_5_through_13_without_examples(
    template_path: Path,
    record: MasterDataRecord,
    tmp_path: Path,
) -> None:
    records = [
        MasterDataRecord(
            item_number=f"128192203{index:02d}",
            m3_name=f"PRODUCT {index}",
        )
        for index in range(1, 10)
    ]
    output = tmp_path / "MASTERDATA.xlsx"
    MasterDataExcelExporter(
        template_path,
        reference_template_path=template_path,
    ).export(records, output)
    sheet = load_workbook(output, data_only=False)["Master template"]

    assert [sheet[f"B{row}"].value for row in range(5, 14)] == [
        item.item_number for item in records
    ]
    assert all(sheet[f"A{row}"].value != "EXAMPLE" for row in range(5, 14))
    assert sheet["B14"].value is None
    for row in range(5, 14):
        assert sheet[f"D{row}"].value == f"=LEN(C{row})"
        assert sheet[f"F{row}"].value == f"=LEN(E{row})"
        assert sheet[f"H{row}"].value == f"=LEN(G{row})"


def test_every_generated_row_uses_exact_authoritative_row_5_styles(
    template_path: Path,
    tmp_path: Path,
) -> None:
    records = [
        MasterDataRecord(
            item_number=f"128192203{index:02d}",
            m3_name=f"PRODUCT {index}",
            item_type="12",
            item_group="128668",
            product_group="12804",
            product_line="128S",
            item_category="741 MKU face powder compact",
        )
        for index in range(1, 10)
    ]
    source_bytes = template_path.read_bytes()
    reference = load_workbook(template_path, data_only=False)["Master template"]
    expected_styles = [reference.cell(5, column)._style for column in range(1, 29)]

    output = tmp_path / "MASTERDATA.xlsx"
    MasterDataExcelExporter(
        template_path,
        reference_template_path=template_path,
    ).export(records, output)
    sheet = load_workbook(output, data_only=False)["Master template"]

    for row in range(5, 14):
        assert [sheet.cell(row, column)._style for column in range(1, 29)] == expected_styles
    assert template_path.read_bytes() == source_bytes


def test_comments_and_data_validation_contract_survive_style_normalization(
    template_path: Path,
    tmp_path: Path,
) -> None:
    records = [
        MasterDataRecord(item_number=f"1280000000{index}", m3_name=f"PRODUCT {index}")
        for index in range(1, 10)
    ]
    output = tmp_path / "MASTERDATA.xlsx"
    MasterDataExcelExporter(
        template_path,
        reference_template_path=template_path,
    ).export(records, output)
    sheet = load_workbook(output, data_only=False)["Master template"]

    assert sheet["A4"].comment is not None
    assert sheet["A4"].comment.text == "Header guidance"
    validations = {
        (validation.type, str(validation.sqref), validation.formula1)
        for validation in sheet.data_validations.dataValidation
    }
    assert (
        "list",
        "I5:I13",
        "'Data for drop downs'!$E$2:$E$20",
    ) in validations
    assert ("textLength", "C5:C13", "30") in validations


def test_only_target_worksheet_part_changes(
    template_path: Path,
    record: MasterDataRecord,
    tmp_path: Path,
) -> None:
    output = tmp_path / "MASTERDATA.xlsx"
    MasterDataExcelExporter(
        template_path,
        reference_template_path=template_path,
    ).export([record], output)
    with ZipFile(template_path) as before, ZipFile(output) as after:
        changed = {name for name in before.namelist() if before.read(name) != after.read(name)}
    assert changed == {"xl/workbook.xml", "xl/worksheets/sheet1.xml"}
