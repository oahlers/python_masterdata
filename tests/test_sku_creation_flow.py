from app.approval import approve_product
from app.import_analyzer import AnalyzedProduct
from app.product_resolver import ProductResolver

from conftest import (
    CONFLICT_EAN,
    EXISTING_ITEM_NUMBER,
    FIRST_CANDIDATE,
    NEW_EAN,
)


def test_new_clarins_product_completes_golden_path(
    monkeypatch,
    source_factory,
    proposal_factory,
    empty_golden_record,
    reservation_db_path,
    reservation_api,
    verification_api,
    candidate_patcher,
):
    source = source_factory(ean=NEW_EAN)
    resolution = ProductResolver(empty_golden_record).resolve(source)
    assert resolution.status == "NEW_PRODUCT"

    proposal = proposal_factory(source)
    analyzed = AnalyzedProduct(
        source_product=source,
        status="READY",
        product_resolution=resolution,
        proposal=proposal,
    )

    candidate_patcher(monkeypatch, [FIRST_CANDIDATE])
    verification_result = verification_api.prepare_for_verification(
        analyzed,
        empty_golden_record,
        reservation_db_path,
    )

    assert verification_result.status == "PREPARED"
    assert verification_result.item_number == FIRST_CANDIDATE
    assert proposal.item_number == FIRST_CANDIDATE
    assert proposal.item_number.startswith("128")
    assert len(proposal.item_number) == 11
    assert proposal.item_number.isdigit()
    assert empty_golden_record.find_by_item_number(proposal.item_number) == []
    assert reservation_api.get(source, reservation_db_path).item_number == proposal.item_number

    approved = approve_product(
        proposal=proposal,
        golden_record=empty_golden_record,
        database_path=reservation_db_path,
        confirmed=True,
    )

    assert approved.approved is True
    assert approved.proposal.item_number == FIRST_CANDIDATE
    assert approved.proposal.brand_code == "128"
    assert approved.proposal.brand_name == "CLARINS"
    assert approved.proposal.mmstat == "10"


def test_identifier_conflict_creates_no_reservation(
    source_factory,
    golden_record,
    reservation_db_path,
    reservation_api,
):
    source = source_factory(
        saether_code=EXISTING_ITEM_NUMBER,
        ean=CONFLICT_EAN,
        product_code="80131396",
    )

    resolution = ProductResolver(golden_record).resolve(source)

    assert resolution.status == "IDENTIFIER_CONFLICT"
    assert reservation_api.get(source, reservation_db_path) is None
    assert not reservation_api.is_reserved(
        EXISTING_ITEM_NUMBER,
        reservation_db_path,
    )
