from conftest import FIRST_CANDIDATE


def test_ready_analyzed_product_is_prepared_and_reserved(
    monkeypatch,
    ready_proposal,
    empty_golden_record,
    reservation_db_path,
    reservation_api,
    verification_api,
    candidate_patcher,
):
    candidate_patcher(monkeypatch, [FIRST_CANDIDATE])
    result = verification_api.prepare(ready_proposal, empty_golden_record, reservation_db_path)
    assert result.status == "PREPARED"
    assert result.item_number == FIRST_CANDIDATE
    assert ready_proposal.item_number == FIRST_CANDIDATE
    reservation = reservation_api.get(ready_proposal.source_product, reservation_db_path)
    assert reservation is not None
    assert reservation.item_number == FIRST_CANDIDATE


def test_review_analyzed_product_cannot_be_prepared(
    ready_proposal,
    empty_golden_record,
    reservation_db_path,
    verification_api,
):
    ready_proposal.needs_review = ["item_class"]
    result = verification_api.prepare(
        ready_proposal,
        empty_golden_record,
        reservation_db_path,
        status="REVIEW",
    )
    assert result.status == "BLOCKED"
    assert result.errors
    assert "READY" in result.errors[0]


def test_existing_product_cannot_be_prepared(
    ready_proposal,
    golden_record,
    reservation_db_path,
    verification_api,
):
    ready_proposal.source_product.ean = "3666057463617"
    result = verification_api.prepare(ready_proposal, golden_record, reservation_db_path)
    assert result.status == "BLOCKED"
    assert result.errors


def test_missing_required_classification_cannot_be_prepared(
    ready_proposal,
    empty_golden_record,
    reservation_db_path,
    verification_api,
):
    ready_proposal.item_group = None
    result = verification_api.prepare(ready_proposal, empty_golden_record, reservation_db_path)
    assert result.status == "BLOCKED"
    assert result.errors
