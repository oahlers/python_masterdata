import pytest

from conftest import FIRST_CANDIDATE, SECOND_CANDIDATE


def test_assigns_verified_prefix_and_persists_reservation(
    monkeypatch,
    ready_proposal,
    empty_golden_record,
    reservation_db_path,
    reservation_api,
    assignment_api,
    candidate_patcher,
):
    candidate_patcher(monkeypatch, [FIRST_CANDIDATE])

    assigned_proposal = assignment_api(
        ready_proposal,
        empty_golden_record,
        reservation_db_path,
    )

    assert assigned_proposal is ready_proposal
    assert ready_proposal.item_number == FIRST_CANDIDATE
    assert reservation_api.is_reserved(FIRST_CANDIDATE, reservation_db_path)


def test_unverified_generation_prefix_blocks_assignment(
    ready_proposal,
    empty_golden_record,
    reservation_db_path,
    assignment_api,
):
    ready_proposal.generation_prefix = None

    with pytest.raises((TypeError, ValueError)):
        assignment_api(ready_proposal, empty_golden_record, reservation_db_path)

    assert ready_proposal.item_number is None


def test_generated_item_number_is_not_in_golden_record(
    monkeypatch,
    ready_proposal,
    empty_golden_record,
    reservation_db_path,
    reservation_api,
    assignment_api,
    candidate_patcher,
):
    candidate_patcher(
        monkeypatch,
        [SECOND_CANDIDATE],
    )

    assigned_proposal = assignment_api(
        ready_proposal,
        empty_golden_record,
        reservation_db_path,
    )

    assert assigned_proposal is ready_proposal

    assert (
        ready_proposal.item_number
        == SECOND_CANDIDATE
    )

    assert (
        empty_golden_record.find_by_item_number(
            SECOND_CANDIDATE
        )
        is None
    )

    reservation = reservation_api.get(
        ready_proposal.source_product,
        reservation_db_path,
    )

    assert reservation is not None

    assert (
        reservation.item_number
        == SECOND_CANDIDATE
    )


def test_reserved_candidate_causes_retry(
    monkeypatch,
    ready_proposal,
    empty_golden_record,
    source_factory,
    reservation_db_path,
    reservation_api,
    assignment_api,
    candidate_patcher,
):
    other_product = source_factory(ean="1111111111111", product_code="PRODUCT-A")
    reservation_api.reserve(other_product, FIRST_CANDIDATE, reservation_db_path)
    candidate_patcher(monkeypatch, [FIRST_CANDIDATE, SECOND_CANDIDATE])

    assigned_proposal = assignment_api(
        ready_proposal,
        empty_golden_record,
        reservation_db_path,
    )

    assert assigned_proposal is ready_proposal
    assert ready_proposal.item_number == SECOND_CANDIDATE
    assert reservation_api.get(other_product, reservation_db_path).item_number == FIRST_CANDIDATE


def test_same_product_gets_same_item_number(
    monkeypatch,
    ready_proposal,
    empty_golden_record,
    reservation_db_path,
    assignment_api,
    candidate_patcher,
):
    candidate_patcher(monkeypatch, [FIRST_CANDIDATE])
    first = assignment_api(
        ready_proposal,
        empty_golden_record,
        reservation_db_path,
    ).item_number

    ready_proposal.item_number = None
    second = assignment_api(
        ready_proposal,
        empty_golden_record,
        reservation_db_path,
    ).item_number

    assert first == FIRST_CANDIDATE
    assert second == first
