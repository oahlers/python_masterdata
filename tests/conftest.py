"""Shared fixtures for the MASTERDATA/SKU regression suite."""
from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
from typing import Any, Callable

import pytest


FIRST_CANDIDATE = "12817743184"
SECOND_CANDIDATE = "12817743185"
EXISTING_ITEM_NUMBER = "1289490174"
EXISTING_EAN = "3666057463617"
CONFLICT_EAN = "3666057483066"
NEW_EAN = "3616300000001"


@dataclass(slots=True)
class SourceProductFixture:
    product_code: str = "80133745"
    ean: str | None = NEW_EAN
    product_name: str = "TEST SI CPCT POWDR GDT U0 5.8G"
    saether_code: str | None = None
    brand_code: str | None = "128"
    brand_name: str | None = "CLARINS"


@dataclass(slots=True)
class M3ProductFixture:
    mmitno: str = EXISTING_ITEM_NUMBER
    ean: str | None = EXISTING_EAN
    product_name: str = "EXISTING CLARINS PRODUCT"
    brand_code: str | None = "128"
    brand_name: str | None = "CLARINS"
    item_type: str | None = "12"
    item_group: str | None = "128668"
    item_class: str | None = "12866874000"
    product_group: str | None = "12804"
    product_line: str | None = "128S"
    item_category: str | None = "741"

    @property
    def item_number(self) -> str:
        return self.mmitno


@dataclass(slots=True)
class ProductProposalFixture:
    source_product: SourceProductFixture

    item_number: str | None = None

    brand_code: str | None = "128"
    brand_name: str | None = "CLARINS"
    generation_prefix: str | None = "128"

    item_type: str | None = "12"
    item_group: str | None = "128668"
    item_class: str | None = "12866874000"
    product_group: str | None = "12804"

    product_line: str | None = "128S"
    item_category: str | None = "741"

    m3_name: str | None = "TEST SI CPCT POWDR GDT U0 5.8G"
    line_2: str | None = None
    receipt_text: str | None = None

    mmstat: str = "10"

    needs_review: tuple[str, ...] | list[str] = ("item_number",)
    status: str = "READY"

class GoldenRecordFixture:
    """Small in-memory Golden Record whose finders return lists."""

    def __init__(self, products: list[M3ProductFixture] | None = None) -> None:
        self.products = list(products or ())

    def add(self, product: M3ProductFixture) -> None:
        self.products.append(product)

    def load(self) -> "GoldenRecordFixture":
        return self

    def find_by_item_number(self, item_number: Any) -> list[M3ProductFixture]:
        wanted = _identifier(item_number)
        return [
            product
            for product in self.products
            if _identifier(product.mmitno) == wanted
        ]

    def find_by_ean(self, ean: Any) -> list[M3ProductFixture]:
        wanted = _identifier(ean)
        return [
            product for product in self.products if _identifier(product.ean) == wanted
        ]

    def __iter__(self):
        return iter(self.products)

    def __len__(self) -> int:
        return len(self.products)


@pytest.fixture
def source_factory():
    def factory(**overrides: Any) -> SourceProductFixture:
        values = {
            "product_code": "80133745",
            "ean": NEW_EAN,
            "product_name": "TEST SI CPCT POWDR GDT U0 5.8G",
            "saether_code": None,
            "brand_code": "128",
            "brand_name": "CLARINS",
        }
        values.update(overrides)
        return SourceProductFixture(**values)

    return factory


@pytest.fixture
def new_source_product(source_factory: Callable[..., SourceProductFixture]) -> SourceProductFixture:
    return source_factory()


@pytest.fixture
def m3_factory():
    def factory(**overrides: Any) -> M3ProductFixture:
        values = {
            "mmitno": EXISTING_ITEM_NUMBER,
            "ean": EXISTING_EAN,
            "product_name": "EXISTING CLARINS PRODUCT",
            "brand_code": "128",
            "brand_name": "CLARINS",
            "item_type": "12",
            "item_group": "128668",
            "item_class": "12866874000",
            "product_group": "12804",
            "product_line": "128S",
            "item_category": "741",
        }
        values.update(overrides)
        return M3ProductFixture(**values)

    return factory


@pytest.fixture
def empty_golden_record() -> GoldenRecordFixture:
    return GoldenRecordFixture()


@pytest.fixture
def golden_record(m3_factory: Callable[..., M3ProductFixture]) -> GoldenRecordFixture:
    return GoldenRecordFixture([m3_factory()])


@pytest.fixture
def proposal_factory(source_factory: Callable[..., SourceProductFixture]):
    def factory(
        source_product: SourceProductFixture | None = None,
        **overrides: Any,
    ) -> ProductProposalFixture:
        source = source_product or source_factory()
        values = {
    "source_product": source,
    "item_number": None,
    "brand_code": source.brand_code,
    "brand_name": source.brand_name,
    "generation_prefix": "128",
    "item_type": "12",
    "item_group": "128668",
    "item_class": "12866874000",
    "product_group": "12804",
    "product_line": "128S",
    "item_category": "741",
    "m3_name": source.product_name,
    "line_2": None,
    "receipt_text": None,
    "mmstat": "10",
    "needs_review": ("item_number",),
    "status": "READY",
}
        values.update(overrides)
        return ProductProposalFixture(**values)

    return factory


@pytest.fixture
def ready_proposal(proposal_factory: Callable[..., ProductProposalFixture]) -> ProductProposalFixture:
    return proposal_factory()


@pytest.fixture
def analyzed_product(ready_proposal: ProductProposalFixture):
    from app.import_analyzer import AnalyzedProduct
    from app.product_resolver import NEW_PRODUCT, ProductResolution

    source = ready_proposal.source_product
    return AnalyzedProduct(
        source_product=source,
        status="READY",
        product_resolution=ProductResolution(
            status=NEW_PRODUCT,
            source_product=source,
        ),
        proposal=ready_proposal,
    )


@pytest.fixture
def reservation_db_path(tmp_path: Path) -> Path:
    return tmp_path / "item_number_reservations.sqlite3"


@pytest.fixture
def reservation_api():
    return importlib.import_module("app.item_number_reservation")


@pytest.fixture
def generator_api():
    from app.item_number_generator import generate_item_number

    return generate_item_number


@pytest.fixture
def assignment_api():
    from app.item_number_service import assign_item_number

    def assign(proposal, golden_record, database_path):
        assign_item_number(
            proposal,
            golden_record,
            database_path,
            verified_generation_prefix=proposal.generation_prefix,
        )
        return proposal

    return assign


@pytest.fixture
def verification_api():
    return importlib.import_module("app.verification")

@pytest.fixture
def verification_api():
    return importlib.import_module("app.verification")


@pytest.fixture
def candidate_patcher():
    """Patch the pure generator seam with a deterministic finite sequence."""

    def patch(
        monkeypatch: pytest.MonkeyPatch,
        candidates: list[str] | tuple[str, ...],
    ):
        values = tuple(str(candidate) for candidate in candidates)

        def generated(_prefix: str, _count: int = 100):
            yield from values

        module = importlib.import_module("app.item_number_generator")
        monkeypatch.setattr(module, "generate_item_number_candidates", generated)
        return values

    return patch


def _identifier(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None
