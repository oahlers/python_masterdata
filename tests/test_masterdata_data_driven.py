from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import warnings

from openpyxl import load_workbook

from app.masterdata_builder import MasterDataBuilder
from app.masterdata_excel import MasterDataExcelExporter
from app.masterdata_reference import (
    ItemCategoryReference,
    ProductLineReference,
    TemplateReferenceData,
)


@dataclass
class SourceProduct:
    product_code: str
    product_name: str
    ean: str
    brand_code: str
    brand_name: str
    m3_description: str | None = None
    receipt_text: str | None = None


@dataclass
class Proposal:
    item_number: str
    item_type: str = "12"
    item_group: str | None = None
    item_class: str | None = None
    brand_code: str = "128"
    brand_name: str = "Clarins"
    masterdata_review: dict[str, object] = field(default_factory=dict)


@dataclass
class ApprovedProduct:
    source_product: SourceProduct
    proposal: Proposal
    status: str = "APPROVED"


@dataclass
class M3Product:
    mmitno: str
    mmitds: str
    mmfuds: str | None
    mmity: str
    mmitgr: str
    mmitgrtx40: str
    mmitcl: str
    mmitcltx40: str
    mmbuar: str
    mmbuartx40: str
    mmcfi1: str
    mmcfi1tx40: str
    supplier_item_number: str
    receipt_text: str | None = None
    mmstat: str = "20"


@dataclass
class GoldenRecord:
    products: list[M3Product]


def template_reference(
    *,
    brand_code: str = "128",
    brand_name: str = "Clarins",
    category_code: str = "740",
    category_description: str = "MKU face primer",
) -> TemplateReferenceData:
    return TemplateReferenceData(
        product_lines=(
            ProductLineReference(
                brand_code,
                f"{brand_name} spec. products",
            ),
        ),
        item_categories=(
            ItemCategoryReference(
                category_code,
                category_description,
                f"{category_code} {category_description}",
            ),
        ),
    )


def instant_smooth() -> tuple[ApprovedProduct, GoldenRecord]:
    source = SourceProduct(
        product_code="80133626",
        product_name="TEST SI INSTANT SMOOTH 15ML",
        ean="3666057504815",
        brand_code="128",
        brand_name="Clarins",
        m3_description="Instant Smooth perfecting touch",
        receipt_text="INSTANT SMOOTH",
    )
    proposal = Proposal(
        item_number="12819220316",
        item_group="128591",
        item_class="12804",
    )
    row = M3Product(
        mmitno="12859174015",
        mmitds="INSTANT SMOOTH 15ML",
        mmfuds="Instant Smooth perfecting touch",
        mmity="12",
        mmitgr="128591",
        mmitgrtx40="Instant Smooth",
        mmitcl="12804",
        mmitcltx40="Make-up",
        mmbuar="128",
        mmbuartx40="Clarins",
        mmcfi1="740",
        mmcfi1tx40="MKU face primer",
        supplier_item_number="80133626",
        receipt_text="INSTANT SMOOTH",
    )
    return ApprovedProduct(source, proposal), GoldenRecord([row])


def compact_powder() -> tuple[ApprovedProduct, GoldenRecord]:
    source = SourceProduct(
        product_code="80133745",
        product_name="TEST SI CPCT POWDR GDT U0",
        ean="3666057505959",
        brand_code="128",
        brand_name="Clarins",
        m3_description="U0 neutral very light",
        receipt_text="SI POWDER U0",
    )
    proposal = Proposal(
        item_number="12817743184",
        item_group="128668",
        item_class="12804",
    )
    row = M3Product(
        mmitno="128668741U0",
        mmitds="SI CPCT POWDR GDT U0",
        mmfuds="U0 neutral very light",
        # Real M3 retail sibling.  The incoming novelty is a tester (12), while
        # the documented retail family member is a standard item (00).
        mmity="00",
        mmitgr="128668",
        mmitgrtx40="Skin Illusion Compact Powder",
        mmitcl="12804",
        mmitcltx40="Make-up",
        mmbuar="128",
        mmbuartx40="Clarins",
        mmcfi1="741",
        mmcfi1tx40="MKU face powder compact",
        supplier_item_number="80133745",
        receipt_text="SI POWDER U0",
    )
    return ApprovedProduct(source, proposal), GoldenRecord([row])


def test_instant_smooth_semantics_are_derived_from_data() -> None:
    product, golden = instant_smooth()
    record = MasterDataBuilder(
        golden_record=golden,
        template_reference=template_reference(),
    ).build(product)

    assert record.product_line == "128S"
    assert record.item_category == "740 MKU face primer"
    assert record.item_group == "128591"
    assert record.product_group == "12804"
    assert record.item_group_description is None
    assert record.item_group_evidence_description == "Instant Smooth"
    assert record.m3_name == "TEST SI INSTANT SMOOTH 15ML"
    assert record.m3_description == "Instant Smooth perfecting touch"
    assert record.receipt_text is None
    assert record.receipt_text_status == "not_applicable"


def test_compact_powder_semantics_are_derived_from_data() -> None:
    product, golden = compact_powder()
    record = MasterDataBuilder(
        golden_record=golden,
        template_reference=template_reference(
            category_code="741",
            category_description="MKU face powder compact",
        ),
    ).build(product)

    assert record.product_line == "128S"
    assert record.item_type == "12"
    assert record.item_category == "741 MKU face powder compact"
    assert record.item_group == "128668"
    assert record.product_group == "12804"
    assert record.item_group_description is None
    assert (
        record.item_group_evidence_description
        == "Skin Illusion Compact Powder"
    )


def test_real_tester_uses_retail_sibling_despite_different_mmity() -> None:
    product, golden = compact_powder()

    first = MasterDataBuilder(
        golden_record=golden,
        template_reference=template_reference(
            category_code="741",
            category_description="MKU face powder compact",
        ),
    ).build(product)

    assert product.proposal.item_type == "12"
    assert golden.products[0].mmity == "00"
    assert first.item_type == "12"
    assert first.item_category == "741 MKU face powder compact"
    assert first.evidence_item_numbers == ("128668741U0",)

    retail = golden.products[0]
    golden.products[0] = M3Product(
        **{
            **retail.__dict__,
            "mmcfi1": "749",
            "mmcfi1tx40": "Changed compact category",
        }
    )
    second = MasterDataBuilder(
        golden_record=golden,
        template_reference=template_reference(
            category_code="749",
            category_description="Changed compact category",
        ),
    ).build(product)

    assert second.item_category == "749 Changed compact category"


def test_mapping_changes_when_golden_record_and_template_change() -> None:
    source = SourceProduct(
        product_code="REF-9",
        product_name="EXAMPLE VARIANT V9",
        ean="9000000000009",
        brand_code="777",
        brand_name="Example Brand",
        m3_description="Documented variant nine",
        receipt_text="EXAMPLE V9",
    )
    product = ApprovedProduct(
        source,
        Proposal(
            item_number="77700000009",
            item_group="777900",
            item_class="77709",
            brand_code="777",
            brand_name="Example Brand",
        ),
    )
    golden = GoldenRecord(
        [
            M3Product(
                mmitno="77790099909",
                mmitds="EXAMPLE VARIANT V9",
                mmfuds="Documented variant nine",
                mmity="12",
                mmitgr="777900",
                mmitgrtx40="Example family",
                mmitcl="77709",
                mmitcltx40="Example group",
                mmbuar="777",
                mmbuartx40="Example Brand",
                mmcfi1="999",
                mmcfi1tx40="Example category",
                supplier_item_number="REF-9",
                receipt_text="EXAMPLE V9",
            )
        ]
    )
    record = MasterDataBuilder(
        golden_record=golden,
        template_reference=template_reference(
            brand_code="777",
            brand_name="Example Brand",
            category_code="999",
            category_description="Example category",
        ),
    ).build(product)

    assert record.item_group == "777900"
    assert record.product_group == "77709"
    assert record.product_line == "777S"
    assert record.item_category == "999 Example category"
    assert record.item_group_evidence_description == "Example family"


def test_conflicting_strongest_siblings_leave_category_for_review() -> None:
    product, golden = compact_powder()
    conflicting = golden.products[0]
    golden.products.append(
        M3Product(
            **{
                **conflicting.__dict__,
                "mmitno": "128668742U0",
                "mmcfi1": "742",
                "mmcfi1tx40": "Different compact category",
            }
        )
    )
    reference = TemplateReferenceData(
        product_lines=(ProductLineReference("128", "Clarins spec. products"),),
        item_categories=(
            ItemCategoryReference(
                "741",
                "MKU face powder compact",
                "741 MKU face powder compact",
            ),
            ItemCategoryReference(
                "742",
                "Different compact category",
                "742 Different compact category",
            ),
        ),
    )

    record = MasterDataBuilder(
        golden_record=golden,
        template_reference=reference,
    ).build(product)

    assert record.item_category is None
    assert "item_category" in record.review_fields


def test_missing_or_ambiguous_description_evidence_is_not_guessed() -> None:
    product, golden = compact_powder()
    product.source_product.m3_description = None
    product.source_product.receipt_text = None
    base = golden.products[0]
    golden.products = [
        M3Product(**{**base.__dict__, "mmitno": "A", "mmfuds": "Shade A"}),
        M3Product(**{**base.__dict__, "mmitno": "B", "mmfuds": "Shade B"}),
    ]

    record = MasterDataBuilder(
        golden_record=golden,
        template_reference=template_reference(
            category_code="741",
            category_description="MKU face powder compact",
        ),
    ).build(product)

    assert record.m3_description is None
    assert record.receipt_text is None
    assert "m3_description" in record.review_fields
    assert "receipt_text" not in record.review_fields
    assert record.receipt_text_status == "not_applicable"


def test_long_supplier_name_is_not_blindly_truncated() -> None:
    product, golden = instant_smooth()
    product.source_product.product_name = (
        "THIS DOCUMENTED SUPPLIER NAME IS LONGER THAN THIRTY CHARACTERS"
    )
    golden.products[0].mmitds = ""

    record = MasterDataBuilder(
        golden_record=golden,
        template_reference=template_reference(),
    ).build(product)

    assert record.m3_name is None
    assert "m3_name" in record.review_fields


def test_new_item_group_description_requires_explicit_review() -> None:
    product, golden = instant_smooth()
    product.proposal.masterdata_review = {
        "item_group": "128999",
        "is_new_item_group": True,
        "item_group_description": "Reviewed new family",
    }
    golden.products = []

    record = MasterDataBuilder(
        golden_record=golden,
        template_reference=template_reference(),
    ).build(product)

    assert record.item_group == "128999"
    assert record.item_group_description == "Reviewed new family"


def test_excel_columns_c_e_g_m_n_and_blank_existing_group_description(
    tmp_path: Path,
) -> None:
    product, golden = instant_smooth()
    record = MasterDataBuilder(
        golden_record=golden,
        template_reference=template_reference(),
    ).build(product)

    template = Path("templates/saether_masterdata_template.xlsx")
    output = tmp_path / "MASTERDATA_data_driven.xlsx"
    MasterDataExcelExporter(template).export([record], output)

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Data Validation extension is not supported and will be removed",
            category=UserWarning,
            module="openpyxl.worksheet._reader",
        )
        sheet = load_workbook(output, data_only=False)["Master template"]
    assert sheet["C5"].value == "TEST SI INSTANT SMOOTH 15ML"
    assert sheet["E5"].value == "Instant Smooth perfecting touch"
    assert sheet["G5"].value is None
    assert sheet["K5"].value is None
    assert sheet["M5"].value == "128S"
    assert sheet["N5"].value == "740 MKU face primer"
    assert sheet["D5"].value == "=LEN(C5)"
    assert sheet["F5"].value == "=LEN(E5)"
    assert sheet["H5"].value == "=LEN(G5)"
