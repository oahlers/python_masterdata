from app.product_resolver import ProductResolver

from conftest import CONFLICT_EAN, EXISTING_EAN, EXISTING_ITEM_NUMBER, NEW_EAN


def test_existing_ean_is_existing_product(golden_record, source_factory):
    product = source_factory(ean=EXISTING_EAN)

    result = ProductResolver(golden_record).resolve(product)

    assert result.status == "EXISTING_PRODUCT"


def test_unknown_ean_is_new_product(golden_record, source_factory):
    product = source_factory(ean=NEW_EAN)

    result = ProductResolver(golden_record).resolve(product)

    assert result.status == "NEW_PRODUCT"


def test_incoming_item_number_with_different_ean_is_identifier_conflict(
    golden_record,
    source_factory,
):
    product = source_factory(
        saether_code=EXISTING_ITEM_NUMBER,
        ean=CONFLICT_EAN,
        product_code="80131396",
    )

    result = ProductResolver(golden_record).resolve(product)

    assert result.status == "IDENTIFIER_CONFLICT"


def test_matching_item_number_and_ean_is_existing_product(
    golden_record,
    source_factory,
):
    product = source_factory(
        saether_code=EXISTING_ITEM_NUMBER,
        ean=EXISTING_EAN,
    )

    result = ProductResolver(golden_record).resolve(product)

    assert result.status == "EXISTING_PRODUCT"


def test_duplicate_ean_is_ambiguous(
    golden_record,
    m3_factory,
    source_factory,
):
    golden_record.add(
        m3_factory(
            mmitno="12800000000",
            ean=EXISTING_EAN,
        )
    )

    result = ProductResolver(golden_record).resolve(
        source_factory(ean=EXISTING_EAN)
    )

    assert result.status == "AMBIGUOUS"
    assert len(result.existing_products) == 2
