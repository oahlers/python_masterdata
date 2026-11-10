import pytest

from app.approval import approve_product, validate_proposal_for_approval

from conftest import FIRST_CANDIDATE, SECOND_CANDIDATE


def test_approval_requires_explicit_confirmation(
    ready_proposal,
    empty_golden_record,
    reservation_db_path,
):
    with pytest.raises(ValueError, match="eksplicit"):
        approve_product(
            proposal=ready_proposal,
            golden_record=empty_golden_record,
            database_path=reservation_db_path,
            confirmed=False,
        )


def test_unreserved_proposal_is_blocked(
    ready_proposal,
    empty_golden_record,
    reservation_db_path,
):
    ready_proposal.item_number = FIRST_CANDIDATE

    errors = validate_proposal_for_approval(
        proposal=ready_proposal,
        golden_record=empty_golden_record,
        database_path=reservation_db_path,
    )

    assert any("persistent reserveret" in error for error in errors)


def test_pending_review_is_blocked(
    ready_proposal,
    empty_golden_record,
    reservation_db_path,
    reservation_api,
):
    ready_proposal.item_number = FIRST_CANDIDATE
    ready_proposal.needs_review = ["item_class"]
    reservation_api.reserve(
        ready_proposal.source_product,
        FIRST_CANDIDATE,
        reservation_db_path,
    )

    errors = validate_proposal_for_approval(
        proposal=ready_proposal,
        golden_record=empty_golden_record,
        database_path=reservation_db_path,
    )

    assert any("kræver review" in error for error in errors)


def test_mismatched_persistent_reservation_is_blocked(
    ready_proposal,
    empty_golden_record,
    reservation_db_path,
    reservation_api,
):
    reservation_api.reserve(
        ready_proposal.source_product,
        FIRST_CANDIDATE,
        reservation_db_path,
    )
    ready_proposal.item_number = SECOND_CANDIDATE

    errors = validate_proposal_for_approval(
        proposal=ready_proposal,
        golden_record=empty_golden_record,
        database_path=reservation_db_path,
    )

    assert any("matcher ikke" in error for error in errors)


def test_valid_reserved_proposal_can_be_approved(
    ready_proposal,
    empty_golden_record,
    reservation_db_path,
    reservation_api,
):
    ready_proposal.item_number = FIRST_CANDIDATE
    reservation_api.reserve(
        ready_proposal.source_product,
        FIRST_CANDIDATE,
        reservation_db_path,
    )

    approved = approve_product(
        proposal=ready_proposal,
        golden_record=empty_golden_record,
        database_path=reservation_db_path,
        confirmed=True,
    )

    assert approved.approved is True
    assert approved.proposal is ready_proposal
    assert approved.approval_source == "user"
    assert approved.approved_at


def test_revalidation_blocks_ean_that_appears_after_preparation(
    ready_proposal,
    empty_golden_record,
    m3_factory,
    reservation_db_path,
    reservation_api,
):
    ready_proposal.item_number = FIRST_CANDIDATE
    reservation_api.reserve(
        ready_proposal.source_product,
        FIRST_CANDIDATE,
        reservation_db_path,
    )
    empty_golden_record.add(
        m3_factory(
            mmitno="12899999999",
            ean=ready_proposal.source_product.ean,
        )
    )

    with pytest.raises(ValueError, match="Golden Record"):
        approve_product(
            proposal=ready_proposal,
            golden_record=empty_golden_record,
            database_path=reservation_db_path,
            confirmed=True,
        )
