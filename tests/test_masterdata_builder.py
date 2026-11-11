from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.masterdata_builder import MasterDataBuilder
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
    m3_description: str | None = None
    receipt_text: str | None = None


@dataclass
class Proposal:
    item_number: str | None
    item_type: str
    item_group: str
    item_class: str
    brand_code: str
    brand_name: str
    masterdata_review: dict[str, object] = field(default_factory=dict)


@dataclass
class ApprovedProduct:
    source_product: SourceProduct
    proposal: Proposal
    status: str = "APPROVED"


@dataclass
class M3Row:
    mmitno: str
    mmitds: str
    mmfuds: str
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
    receipt_text: str
    mmstat: str = "20"


@dataclass
class GoldenRecord:
    products: list[M3Row]


@pytest.fixture
def reference() -> TemplateReferenceData:
    return TemplateReferenceData(
        product_lines=(
            ProductLineReference("501", "Example Beauty spec. products"),
        ),
        item_categories=(
            ItemCategoryReference("880", "Example category", "880 Example category"),
        ),
    )


@pytest.fixture
def approved_product() -> ApprovedProduct:
    return ApprovedProduct(
        SourceProduct(
            product_code="REF-1",
            product_name="EXAMPLE PRODUCT V1",
            ean="5700000000001",
            m3_description="Variant one",
            receipt_text="EXAMPLE V1",
        ),
        Proposal(
            item_number="50100000001",
            item_type="12",
            item_group="501100",
            item_class="50101",
            brand_code="501",
            brand_name="Example Beauty",
        ),
    )


@pytest.fixture
def golden_record() -> GoldenRecord:
    return GoldenRecord(
        [
            M3Row(
                mmitno="50110088001",
                mmitds="EXAMPLE PRODUCT V1",
                mmfuds="Variant one",
                mmity="12",
                mmitgr="501100",
                mmitgrtx40="Example family",
                mmitcl="50101",
                mmitcltx40="Example group",
                mmbuar="501",
                mmbuartx40="Example Beauty",
                mmcfi1="880",
                mmcfi1tx40="Example category",
                supplier_item_number="REF-1",
                receipt_text="EXAMPLE V1",
            )
        ]
    )


def test_builds_from_golden_record_and_template_without_changing_sku(
    approved_product: ApprovedProduct,
    golden_record: GoldenRecord,
    reference: TemplateReferenceData,
) -> None:
    record = MasterDataBuilder(
        golden_record=golden_record,
        template_reference=reference,
    ).build(approved_product)

    assert record.item_number == approved_product.proposal.item_number
    assert record.item_group == "501100"
    assert record.product_group == "50101"
    assert record.product_line == "501S"
    assert record.item_category == "880 Example category"
    assert record.item_group_description is None
    assert record.item_group_evidence_description == "Example family"
    assert record.m3_name == "EXAMPLE PRODUCT V1"
    assert record.m3_description == "Variant one"
    assert record.receipt_text is None
    assert record.receipt_text_status == "not_applicable"
    assert record.receipt_text_reason == "Item type 12 is a tester."
    assert "receipt_text" not in record.review_fields


def test_rejects_non_approved_product(
    approved_product: ApprovedProduct,
    golden_record: GoldenRecord,
    reference: TemplateReferenceData,
) -> None:
    approved_product.status = "PREPARED"
    with pytest.raises(ValueError, match="Only APPROVED products"):
        MasterDataBuilder(
            golden_record=golden_record,
            template_reference=reference,
        ).build(approved_product)


def test_ready_preview_before_item_number_generation_keeps_dynamic_values(
    approved_product: ApprovedProduct,
    golden_record: GoldenRecord,
    reference: TemplateReferenceData,
) -> None:
    approved_product.status = "READY"
    approved_product.proposal.item_number = None
    builder = MasterDataBuilder(
        golden_record=golden_record,
        template_reference=reference,
    )

    preview = builder.build_preview(approved_product)

    assert preview.item_number is None
    assert preview.m3_name == "EXAMPLE PRODUCT V1"
    assert preview.product_line == "501S"
    assert preview.item_category == "880 Example category"
    assert preview.evidence_item_numbers == ("50110088001",)
    assert preview.missing_preverification_fields == ()
    assert preview.ready_for_verification is True
    assert preview.missing_required_fields == ("item_number",)
    assert preview.ready_for_approval is False

    approved_product.status = "APPROVED"
    with pytest.raises(ValueError, match="proposal.item_number is required"):
        builder.build(approved_product)


def test_does_not_truncate_long_supplier_name(
    approved_product: ApprovedProduct,
    golden_record: GoldenRecord,
    reference: TemplateReferenceData,
) -> None:
    approved_product.source_product.product_name = "A SUPPLIER NAME THAT IS DEFINITELY TOO LONG"
    golden_record.products[0].mmitds = ""
    record = MasterDataBuilder(
        golden_record=golden_record,
        template_reference=reference,
    ).build(approved_product)
    assert record.m3_name is None
    assert "m3_name" in record.review_fields


def test_optional_masterdata_fields_do_not_block_reserved_sku_or_approval_gate(
    approved_product: ApprovedProduct,
    golden_record: GoldenRecord,
    reference: TemplateReferenceData,
) -> None:
    approved_product.source_product.m3_description = None
    approved_product.source_product.receipt_text = None
    golden_record.products[0].mmity = "00"
    golden_record.products[0].mmfuds = ""
    golden_record.products[0].receipt_text = ""

    record = MasterDataBuilder(
        golden_record=golden_record,
        template_reference=reference,
    ).build(approved_product)

    assert record.item_number == "50100000001"
    assert record.item_type == "12"
    assert record.m3_description is None
    assert record.receipt_text is None
    assert record.missing_required_fields == ()
    assert record.ready_for_approval is True
    assert record.warning_fields == ("m3_description",)
    assert record.receipt_text_status == "not_applicable"


def test_minimum_gate_blocks_missing_identity_but_not_optional_fields(
    approved_product: ApprovedProduct,
    golden_record: GoldenRecord,
    reference: TemplateReferenceData,
) -> None:
    approved_product.source_product.ean = ""
    approved_product.source_product.m3_description = None
    approved_product.source_product.receipt_text = None
    golden_record.products[0].mmfuds = ""
    golden_record.products[0].receipt_text = ""

    record = MasterDataBuilder(
        golden_record=golden_record,
        template_reference=reference,
    ).build(approved_product)

    assert record.missing_required_fields == ("ean",)
    assert "m3_description" in record.warning_fields
    assert "receipt_text" not in record.warning_fields


def test_sales_item_requires_receipt_text(
    approved_product: ApprovedProduct,
    golden_record: GoldenRecord,
    reference: TemplateReferenceData,
) -> None:
    approved_product.proposal.item_type = "00"
    approved_product.source_product.receipt_text = None
    golden_record.products[0].mmity = "00"
    golden_record.products[0].receipt_text = ""

    record = MasterDataBuilder(
        golden_record=golden_record,
        template_reference=reference,
    ).build(approved_product)

    assert record.receipt_text is None
    assert record.receipt_text_status == "missing_documented_source"
    assert record.receipt_text_required is True
    assert "receipt_text" in record.missing_required_fields
    assert "receipt_text" not in record.warning_fields
    assert record.ready_for_approval is False



def test_missing_brand_code_and_name_are_blocking_minimum_requirements(
    approved_product: ApprovedProduct,
    golden_record: GoldenRecord,
    reference: TemplateReferenceData,
) -> None:
    approved_product.status = "READY"
    approved_product.proposal.item_number = None
    approved_product.proposal.brand_code = ""
    approved_product.proposal.brand_name = ""

    preview = MasterDataBuilder(
        golden_record=golden_record,
        template_reference=reference,
    ).build_preview(approved_product)

    assert preview.brand_code is None
    assert preview.brand_name is None
    assert "brand_code" in preview.missing_preverification_fields
    assert "brand_name" in preview.missing_preverification_fields
    assert preview.ready_for_verification is False
