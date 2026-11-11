from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from app.masterdata_reference import TemplateReferenceData


def _reference_workbook(path: Path) -> Path:
    workbook = Workbook()
    workbook.active.title = "Master template"
    product_lines = workbook.create_sheet("Product line")
    categories = workbook.create_sheet("Data for drop downs")
    workbook.create_sheet("Kategorioversigt")
    workbook.create_sheet("Link til guide")

    product_lines.append([])
    product_lines.append(["AGr", "Description"])
    product_lines.append(["128", "Clarins spec. products"])
    product_lines.append(["348", "FENTY BEAUTY spec. products"])

    categories.append(["Item category", "Description", "Combined"])
    categories.append(["740", "MKU face primer", '=CONCAT(A2," ",B2)'])
    categories.append(["741", "MKU face powder compact", None])
    workbook.save(path)
    return path


def test_reference_option_payloads_are_non_empty_selectable_and_stable(
    tmp_path: Path,
) -> None:
    path = _reference_workbook(tmp_path / "saether_masterdata_template_reference.xlsx")

    reference = TemplateReferenceData.from_xlsx(path)

    assert reference.product_line_option_payload() == [
        {"value": "128S", "label": "128S — Clarins spec. products"},
        {"value": "348S", "label": "348S — FENTY BEAUTY spec. products"},
    ]
    # Formula cells without a cached Excel result still fall back to the
    # authoritative code + description columns instead of becoming blank.
    assert reference.item_category_option_payload() == [
        {"value": "740 MKU face primer", "label": "740 MKU face primer"},
        {
            "value": "741 MKU face powder compact",
            "label": "741 MKU face powder compact",
        },
    ]


def test_option_payloads_deduplicate_values_without_losing_workbook_order() -> None:
    from app.masterdata_reference import (
        ItemCategoryReference,
        ProductLineReference,
    )

    reference = TemplateReferenceData(
        product_lines=(
            ProductLineReference("128", "Clarins spec. products"),
            ProductLineReference("128S", "Clarins spec. products"),
        ),
        item_categories=(
            ItemCategoryReference("741", "MKU face powder compact", "741 MKU face powder compact"),
            ItemCategoryReference("741", "MKU face powder compact", "741 MKU face powder compact"),
        ),
    )

    assert [item["value"] for item in reference.product_line_option_payload()] == ["128S"]
    assert [item["value"] for item in reference.item_category_option_payload()] == [
        "741 MKU face powder compact"
    ]
