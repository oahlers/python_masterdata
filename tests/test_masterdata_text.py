from __future__ import annotations

from dataclasses import dataclass, field

from app.masterdata_text import resolve_m3_text


@dataclass
class SourceProduct:
    product_name: str
    m3_description: str | None = None
    receipt_text: str | None = None
    product_description: str | None = None


@dataclass
class Proposal:
    item_type: str | None
    masterdata_review: dict[str, object] = field(default_factory=dict)


@dataclass
class M3Row:
    mmitds: str = ""
    mmfuds: str = ""
    receipt_text: str = ""


def test_tester_uses_supplier_name_but_never_inherits_receipt_text() -> None:
    result = resolve_m3_text(
        Proposal(item_type="12"),
        SourceProduct(
            product_name="TEST SI CPCT POWDR GDT U0 5.8G",
            receipt_text="RETAIL POWDER U0",
        ),
        [M3Row(receipt_text="RETAIL POWDER U0")],
        item_type="12",
    )

    assert result.m3_name == "TEST SI CPCT POWDR GDT U0 5.8G"
    assert result.m3_name_source == "supplier_product_name"
    assert result.receipt_text is None
    assert result.receipt_text_status == "not_applicable"
    assert result.receipt_text_source == "item_type_rule"
    assert result.receipt_text_required is False
    assert "receipt_text" not in result.review_fields


def test_missing_line_2_is_visible_without_guessing() -> None:
    result = resolve_m3_text(
        Proposal(item_type="12"),
        SourceProduct(product_name="TEST PRODUCT"),
        (),
        item_type="12",
    )

    assert result.m3_description is None
    assert result.m3_description_status == "missing_documented_source"
    assert "m3_description" in result.review_fields


def test_sales_item_missing_receipt_text_requires_review() -> None:
    result = resolve_m3_text(
        Proposal(item_type="00"),
        SourceProduct(product_name="RETAIL PRODUCT"),
        (),
        item_type="00",
    )

    assert result.receipt_text is None
    assert result.receipt_text_required is True
    assert result.receipt_text_status == "missing_documented_source"
    assert "receipt_text" in result.review_fields


def test_unknown_item_type_defers_receipt_text_applicability() -> None:
    result = resolve_m3_text(
        Proposal(item_type=None),
        SourceProduct(
            product_name="SI CPCT POWDER BRUSH TEST",
            receipt_text="SHOULD NOT BE USED YET",
        ),
        (),
        item_type=None,
    )

    assert result.receipt_text is None
    assert result.receipt_text_required is False
    assert result.receipt_text_status == "awaiting_item_type"
    assert result.receipt_text_source == "item_type_rule"
    assert "receipt_text" not in result.review_fields


def test_free_form_product_description_is_not_treated_as_line_2() -> None:
    result = resolve_m3_text(
        Proposal(item_type="12"),
        SourceProduct(
            product_name="TEST PRODUCT",
            product_description="Long text from a special workbook schema",
        ),
        (),
        item_type="12",
    )

    assert result.m3_description is None
    assert result.m3_description_status == "missing_documented_source"
    assert result.m3_description_source is None


def test_long_supplier_name_is_not_truncated() -> None:
    result = resolve_m3_text(
        Proposal(item_type="12"),
        SourceProduct(
            product_name="THIS DOCUMENTED SUPPLIER NAME IS LONGER THAN THIRTY"
        ),
        (),
        item_type="12",
    )

    assert result.m3_name is None
    assert result.m3_name_status == "review_required_length"
    assert "not truncated" in (result.m3_name_reason or "")
    assert "m3_name" in result.review_fields
