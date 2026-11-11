from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.approval import approve_product
from app.masterdata_lifecycle import (
    CODE_READY,
    IDENTITY_CONFLICT,
    IDENTITY_REVIEW,
    MASTERDATA_REVIEW,
    READY_FOR_APPROVAL,
    lifecycle_state,
)


def _item(*, status="REVIEW", item_number=None, brand_code="135", brand_name="JPG"):
    return SimpleNamespace(
        status=status,
        source_product=SimpleNamespace(
            ean="8435415099991",
            product_code="JPG27001",
            product_name="LE MALE ELIXIR EDP 75ML",
        ),
        proposal=SimpleNamespace(
            item_number=item_number,
            brand_code=brand_code,
            brand_name=brand_name,
            needs_review=("item_group", "item_class", "product_line"),
        ),
    )


def test_identity_and_code_reservation_are_separate_from_masterdata() -> None:
    missing_brand = _item(brand_code="", brand_name="")
    assert lifecycle_state(missing_brand).stage == IDENTITY_REVIEW

    code_ready = _item()
    state = lifecycle_state(
        code_ready,
        {"blocking_fields": ["item_group", "product_line", "item_category"]},
    )
    assert state.stage == CODE_READY
    assert state.can_reserve_code is True

    reserved = _item(item_number="13599999999")
    state = lifecycle_state(
        reserved,
        {"blocking_fields": ["item_group", "product_line", "item_category"]},
    )
    assert state.stage == MASTERDATA_REVIEW
    assert state.blockers == ("item_group", "product_line", "item_category")

    state = lifecycle_state(reserved, {"blocking_fields": []})
    assert state.stage == READY_FOR_APPROVAL
    assert state.can_approve is True


def test_identifier_conflict_always_blocks_reservation() -> None:
    state = lifecycle_state(_item(status="AMBIGUOUS"))
    assert state.stage == IDENTITY_CONFLICT
    assert state.can_reserve_code is False


def test_tuple_backed_review_fields_do_not_break_approval() -> None:
    proposal = SimpleNamespace(
        item_number="13599999999",
        brand_code="135",
        brand_name="Jean Paul Gaultier",
        needs_review=("item_number", "m3_description"),
    )
    source = SimpleNamespace(
        ean="8435415099991",
        product_code="JPG27001",
        product_name="LE MALE ELIXIR EDP 75ML",
    )
    golden_record = SimpleNamespace(products=[])

    original_review_fields = proposal.needs_review

    with pytest.raises(ValueError, match="persistent reserveret"):
        approve_product(
            proposal=proposal,
            source_product=source,
            golden_record=golden_record,
            confirmed=True,
        )

    assert proposal.needs_review == original_review_fields
    assert isinstance(proposal.needs_review, tuple)
