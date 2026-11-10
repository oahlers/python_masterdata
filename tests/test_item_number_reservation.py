from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from conftest import FIRST_CANDIDATE, SECOND_CANDIDATE


def test_reservation_is_persistent_across_calls(
    new_source_product,
    reservation_db_path,
    reservation_api,
):
    reservation_api.reserve(new_source_product, FIRST_CANDIDATE, reservation_db_path)

    reopened = reservation_api.get(new_source_product, reservation_db_path)

    assert reopened is not None
    assert reopened.item_number == FIRST_CANDIDATE
    assert reservation_api.is_reserved(FIRST_CANDIDATE, reservation_db_path)


def test_same_product_and_number_is_idempotent(
    new_source_product,
    reservation_db_path,
    reservation_api,
):
    first = reservation_api.reserve(
        new_source_product,
        FIRST_CANDIDATE,
        reservation_db_path,
    )
    second = reservation_api.reserve(
        new_source_product,
        FIRST_CANDIDATE,
        reservation_db_path,
    )

    persisted = reservation_api.get(new_source_product, reservation_db_path)
    assert persisted.item_number == FIRST_CANDIDATE
    assert getattr(first, "item_number", FIRST_CANDIDATE) == FIRST_CANDIDATE
    assert getattr(second, "item_number", FIRST_CANDIDATE) == FIRST_CANDIDATE


def test_item_number_cannot_belong_to_two_products(
    source_factory,
    reservation_db_path,
    reservation_api,
):
    product_a = source_factory(ean="1111111111111", product_code="PRODUCT-A")
    product_b = source_factory(ean="2222222222222", product_code="PRODUCT-B")
    reservation_api.reserve(product_a, FIRST_CANDIDATE, reservation_db_path)

    with pytest.raises((ValueError, RuntimeError, sqlite3.IntegrityError)):
        reservation_api.reserve(product_b, FIRST_CANDIDATE, reservation_db_path)

    assert reservation_api.get(product_a, reservation_db_path).item_number == FIRST_CANDIDATE
    assert reservation_api.get(product_b, reservation_db_path) is None


def test_product_cannot_receive_two_item_numbers(
    new_source_product,
    reservation_db_path,
    reservation_api,
):
    reservation_api.reserve(new_source_product, FIRST_CANDIDATE, reservation_db_path)

    try:
        reservation_api.reserve(new_source_product, SECOND_CANDIDATE, reservation_db_path)
    except Exception:
        pass

    persisted = reservation_api.get(new_source_product, reservation_db_path)
    assert persisted.item_number == FIRST_CANDIDATE
    assert not reservation_api.is_reserved(SECOND_CANDIDATE, reservation_db_path)


def test_two_concurrent_products_have_exactly_one_winner(
    source_factory,
    reservation_db_path,
    reservation_api,
):
    products = [
        source_factory(ean="1111111111111", product_code="PRODUCT-A"),
        source_factory(ean="2222222222222", product_code="PRODUCT-B"),
    ]

    def attempt(product):
        try:
            reservation_api.reserve(product, FIRST_CANDIDATE, reservation_db_path)
            return "success"
        except Exception:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, products))

    assert outcomes.count("success") == 1
    assert outcomes.count("conflict") == 1
    assert sum(
        reservation_api.get(product, reservation_db_path) is not None
        for product in products
    ) == 1
