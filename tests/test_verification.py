from conftest import FIRST_CANDIDATE


def test_ready_analyzed_product_is_prepared_and_reserved(
    monkeypatch,
    analyzed_product,
    empty_golden_record,
    reservation_db_path,
    reservation_api,
    verification_api,
    candidate_patcher,
):
    candidate_patcher(monkeypatch, [FIRST_CANDIDATE])

    result = verification_api.prepare_for_verification(
        analyzed_product,
        empty_golden_record,
        reservation_db_path,
    )

    assert result.status == "PREPARED"
    assert result.item_number == FIRST_CANDIDATE
    assert analyzed_product.proposal.item_number == FIRST_CANDIDATE
    reservation = reservation_api.get(
        analyzed_product.source_product,
        reservation_db_path,
    )
    assert reservation is not None
    assert reservation.item_number == FIRST_CANDIDATE


def test_review_analyzed_product_cannot_be_prepared(
    analyzed_product,
    empty_golden_record,
    reservation_db_path,
    verification_api,
):
    analyzed_product.status = "REVIEW"
    analyzed_product.proposal.needs_review = ("item_class",)

    result = verification_api.prepare_for_verification(
        analyzed_product,
        empty_golden_record,
        reservation_db_path,
    )

    assert result.status == "BLOCKED"
    assert result.errors
    assert "READY" in result.errors[0]


def test_existing_product_cannot_be_prepared(
    analyzed_product,
    golden_record,
    reservation_db_path,
    verification_api,
):
    from app.product_resolver import EXISTING_PRODUCT

    analyzed_product.status = "EXISTING"
    analyzed_product.product_resolution.status = EXISTING_PRODUCT
    analyzed_product.existing_products = list(golden_record.products)

    result = verification_api.prepare_for_verification(
        analyzed_product,
        golden_record,
        reservation_db_path,
    )

    assert result.status == "BLOCKED"
    assert result.errors


def test_missing_required_classification_cannot_be_prepared(
    analyzed_product,
    empty_golden_record,
    reservation_db_path,
    verification_api,
):
    analyzed_product.proposal.item_group = None

    result = verification_api.prepare_for_verification(
        analyzed_product,
        empty_golden_record,
        reservation_db_path,
    )

    assert result.status == "BLOCKED"
    assert result.errors
    assert "item_group" in result.errors[0]


def test_bare_product_proposal_is_not_an_authoritative_verification_input(
    ready_proposal,
    empty_golden_record,
    reservation_db_path,
    verification_api,
):
    result = verification_api.prepare_for_verification(
        ready_proposal,
        empty_golden_record,
        reservation_db_path,
    )

    assert result.status == "BLOCKED"
    assert "AnalyzedProduct" in result.errors[0]
