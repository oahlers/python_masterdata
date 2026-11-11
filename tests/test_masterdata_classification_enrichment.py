from __future__ import annotations

from dataclasses import dataclass

from app.masterdata_classification import derive_documented_classification
from app.masterdata_reference import (
    ItemCategoryReference,
    ProductLineReference,
    TemplateReferenceData,
)


@dataclass
class Source:
    product_code: str
    product_name: str
    brand_code: str
    brand_name: str


@dataclass
class Proposal:
    item_type: str
    item_group: str
    item_class: str
    brand_code: str
    brand_name: str


@dataclass
class Row:
    mmitno: str
    mmitds: str
    mmity: str
    mmitgr: str
    mmitgrtx40: str
    mmitcl: str
    mmbuar: str
    mmbuartx40: str
    mmcfi1: str
    mmcfi1tx40: str
    supplier_item_number: str
    mmstat: str = "20"
    mmfuds: str | None = None


@dataclass
class Golden:
    products: list[Row]


def reference(code: str, name: str, category: str) -> TemplateReferenceData:
    return TemplateReferenceData(
        product_lines=(ProductLineReference(code, f"{name} spec. products"),),
        item_categories=(
            ItemCategoryReference(category, "Category text", f"{category} Category text"),
        ),
    )


def test_direct_sibling_outranks_broad_family_row() -> None:
    proposal = Proposal("12", "900100", "90001", "900", "Data Brand")
    source = Source("DIRECT", "PRODUCT V2", "900", "Data Brand")
    golden = Golden(
        [
            Row("broad", "OTHER", "12", "900100", "Family", "90001", "900", "Data Brand", "111", "Other", "OTHER"),
            Row("direct", "PRODUCT V2", "12", "900100", "Family", "90001", "900", "Data Brand", "222", "Category text", "DIRECT", mmfuds="Variant two"),
        ]
    )
    result = derive_documented_classification(
        proposal,
        golden,
        source_product=source,
        template_reference=reference("900", "Data Brand", "222"),
    )
    assert result.product_line_code == "900S"
    assert result.item_category_combined == "222 Category text"
    assert result.m3_description == "Variant two"


def test_equally_strong_conflict_is_blank_not_majority_vote() -> None:
    proposal = Proposal("12", "900100", "90001", "900", "Data Brand")
    source = Source("DIRECT", "PRODUCT V2", "900", "Data Brand")
    rows = [
        Row(str(index), "PRODUCT V2", "12", "900100", "Family", "90001", "900", "Data Brand", category, "Category text", "DIRECT")
        for index, category in enumerate(("222", "223", "223"), start=1)
    ]
    result = derive_documented_classification(
        proposal,
        Golden(rows),
        source_product=source,
        template_reference=TemplateReferenceData(
            product_lines=(ProductLineReference("900", "Data Brand spec. products"),),
            item_categories=(
                ItemCategoryReference("222", "Category text", "222 Category text"),
                ItemCategoryReference("223", "Category text", "223 Category text"),
            ),
        ),
    )
    assert result.item_category_code is None
    assert result.item_category_combined is None
    assert "item_category" in result.review_fields
