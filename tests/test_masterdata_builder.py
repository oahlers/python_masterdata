from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.masterdata_builder import MasterDataBuilder


@dataclass
class SourceProduct:
    product_code: str
    product_name: str
    ean: str
    raw_data: dict[str, object]


@dataclass
class ProductProposal:
    item_number: str
    item_type: str
    item_group: str
    item_class: str
    product_line: str


@dataclass
class ApprovedProduct:
    source_product: SourceProduct
    proposal: ProductProposal
    status: str = "APPROVED"


@pytest.fixture
def approved_product() -> ApprovedProduct:
    return ApprovedProduct(
        source_product=SourceProduct(
            product_code="80133626",
            product_name="TEST SI INSTANT SMOOTH 15ML",
            ean="3666057504815",
            raw_data={
                "_source_sheet": "COMPACT POWDER",
                "_source_row": 20,
            },
        ),
        proposal=ProductProposal(
            item_number="12819220316",
            item_type="12",
            item_group="128591",
            item_class="12804",
            product_line="MKU face primer",
        ),
    )


def test_builds_documented_masterdata_fields(
    approved_product: ApprovedProduct,
) -> None:
    record = MasterDataBuilder().build(approved_product)

    assert record.item_number == "12819220316"
    assert record.m3_name == "TEST SI INSTANT SMOOTH 15ML"
    assert record.item_type == "12"
    assert record.item_group == "128591"
    assert record.item_group_description == "Instant Smooth"
    assert record.product_group == "12804"
    assert record.product_line == "740"
    assert record.ref_number == "80133626"
    assert record.ean == "3666057504815"
    assert record.edition == "NY"


def test_leaves_undocumented_fields_blank(
    approved_product: ApprovedProduct,
) -> None:
    record = MasterDataBuilder().build(approved_product)

    assert record.copy_from_item_number is None
    assert record.m3_description is None
    assert record.receipt_text is None
    assert record.item_category is None
    assert record.net_content is None
    assert record.content_unit is None
    assert record.delivery_week is None
    assert record.supplier_number_for_pos is None
    assert record.gender is None
    assert record.distribution_channel is None
    assert record.cogs is None
    assert record.rrp_dkk is None
    assert record.rrp_sek is None
    assert record.rrp_nok is None
    assert record.rrp_eur is None


def test_does_not_recalculate_the_generated_item_number(
    approved_product: ApprovedProduct,
) -> None:
    approved_product.proposal.item_number = "12819220316"

    record = MasterDataBuilder().build(approved_product)

    assert record.item_number == approved_product.proposal.item_number


def test_rejects_a_product_with_non_approved_status(
    approved_product: ApprovedProduct,
) -> None:
    approved_product.status = "PREPARED"

    with pytest.raises(ValueError, match="Only APPROVED products"):
        MasterDataBuilder().build(approved_product)


def test_normalizes_and_limits_m3_name(
    approved_product: ApprovedProduct,
) -> None:
    approved_product.source_product.product_name = (
        "  this description is longer than thirty characters  "
    )

    record = MasterDataBuilder().build(approved_product)

    assert record.m3_name == "THIS DESCRIPTION IS LONGER THA"
    assert len(record.m3_name) == 30
