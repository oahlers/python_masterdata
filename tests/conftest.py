from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from app import item_number_generator as generator_module
from app import item_number_reservation as reservation_module
from app import item_number_service as service_module
from app import verification as verification_module
from app.import_analyzer import AnalyzedProduct
from app.models import M3Product, ProductProposal, SourceProduct
from app.product_resolver import ProductResolver

NEW_EAN = "3666057504815"
EXISTING_EAN = "3666057463617"
CONFLICT_EAN = "3666057483066"
EXISTING_ITEM_NUMBER = "1289490174"
FIRST_CANDIDATE = "12812345678"
SECOND_CANDIDATE = "12887654321"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _default_for_parameter(parameter: inspect.Parameter) -> Any:
    if parameter.default is not inspect.Parameter.empty:
        return parameter.default
    annotation = str(parameter.annotation).lower()
    if "dict" in annotation:
        return {}
    if "list" in annotation:
        return []
    if "set" in annotation:
        return set()
    if "bool" in annotation:
        return False
    return None


def _construct(cls: type, values: dict[str, Any]):
    signature = inspect.signature(cls)
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if name in values:
            value = values[name]
        elif parameter.default is not inspect.Parameter.empty:
            continue
        else:
            value = _default_for_parameter(parameter)
        if isinstance(value, (dict, list, set)):
            value = value.copy()
        kwargs[name] = value
    return cls(**kwargs)


def make_source_product(**overrides: Any) -> SourceProduct:
    values: dict[str, Any] = {
        "product_code": "80133626",
        "ean": NEW_EAN,
        "product_name": "TEST SI INSTANT SMOOTH 15ML",
        "brand_name": "CLARINS",
        "saether_code": None,
        "product_type": None,
        "source_file": "pytest.xlsx",
        "raw_data": {},
    }
    values.update(overrides)
    return _construct(SourceProduct, values)


def make_m3_product(**overrides: Any) -> M3Product:
    values: dict[str, Any] = {
        "mmitno": EXISTING_ITEM_NUMBER,
        "ean": EXISTING_EAN,
        "mmitds": "EXISTING CLARINS PRODUCT",
        "mmity": "12",
        "mmitgr": "128591",
        "mmitcl": "12804",
        "mmbuar": "128",
        "mmbuartx40": "CLARINS",
        "mmstat": "20",
        "raw_data": {},
    }
    values.update(overrides)
    return _construct(M3Product, values)


def make_proposal(source_product: SourceProduct | None = None, **overrides: Any) -> ProductProposal:
    source_product = source_product or make_source_product()
    values: dict[str, Any] = {
        "source_product": source_product,
        "item_number": None,
        "brand_code": "128",
        "brand_name": "CLARINS",
        "item_group": "128591",
        "item_class": "12804",
        "item_type": "12",
        "product_line": "MKU face primer",
        "mmstat": "10",
        "evidence": {},
        "needs_review": [],
    }
    values.update(overrides)
    return _construct(ProductProposal, values)


class FakeGoldenRecord:
    def __init__(self, products: list[M3Product] | None = None):
        self.products = list(products or [])

    def add(self, product: M3Product | None = None, **values: Any) -> M3Product:
        product = product or make_m3_product(**values)
        self.products.append(product)
        return product

    def find_by_item_number(self, item_number: str | None) -> M3Product | None:
        wanted = _clean(item_number)
        return next((p for p in self.products if _clean(p.mmitno) == wanted), None)

    def find_by_ean(self, ean: str | None) -> list[M3Product]:
        wanted = _clean(ean)
        if wanted is None:
            return []
        return [p for p in self.products if _clean(p.ean) == wanted]

    def find_by_brand_code(self, brand_code: str | None) -> list[M3Product]:
        wanted = _clean(brand_code)
        return [p for p in self.products if _clean(p.mmbuar) == wanted]


def generate_candidate(prefix: str, golden_record: FakeGoldenRecord) -> str:
    return generator_module.generate_item_number(
        generation_prefix=prefix,
        golden_record=golden_record,
        reserved_numbers=set(),
    )


def patch_service_candidates(monkeypatch: pytest.MonkeyPatch, candidates: list[str]) -> None:
    iterator = iter(candidates)

    def deterministic(brand_code: str, golden_record: Any, reserved_numbers: set[str] | None = None) -> str:
        del brand_code, golden_record, reserved_numbers
        return next(iterator)

    monkeypatch.setattr(service_module, "generate_item_number_for_brand", deterministic)


def assign_item_number(proposal: ProductProposal, golden_record: FakeGoldenRecord, database_path: Path) -> ProductProposal:
    result = service_module.assign_item_number(
        proposal=proposal,
        golden_record=golden_record,
        database_path=database_path,
    )
    assert isinstance(result, str)
    assert proposal.item_number == result
    return proposal


def reserve(product: SourceProduct, item_number: str, database_path: Path):
    return reservation_module.reserve_item_number(product=product, item_number=item_number, database_path=database_path)


def get_reservation(product: SourceProduct, database_path: Path):
    return reservation_module.get_reservation_for_product(product=product, database_path=database_path)


def is_reserved(item_number: str, database_path: Path) -> bool:
    return bool(reservation_module.item_number_is_reserved(item_number=item_number, database_path=database_path))


def make_analyzed_product(proposal: ProductProposal, golden_record: FakeGoldenRecord, *, status: str = "READY") -> AnalyzedProduct:
    resolution = ProductResolver(golden_record).resolve(proposal.source_product)
    return AnalyzedProduct(
        source_product=proposal.source_product,
        status=status,
        product_resolution=resolution,
        proposal=proposal,
        family_match=None,
        existing_products=list(resolution.existing_products),
        message="pytest",
    )


def prepare_product(proposal: ProductProposal, golden_record: FakeGoldenRecord, database_path: Path, *, status: str = "READY"):
    item = make_analyzed_product(proposal, golden_record, status=status)
    return verification_module.prepare_single_product(item=item, golden_record=golden_record, database_path=database_path)


def prepared_proposal(result: Any, fallback: ProductProposal) -> ProductProposal:
    return fallback


@pytest.fixture
def reservation_db_path(tmp_path: Path) -> Path:
    return tmp_path / "reservations.db"


@pytest.fixture
def empty_golden_record() -> FakeGoldenRecord:
    return FakeGoldenRecord()


@pytest.fixture
def golden_record() -> FakeGoldenRecord:
    return FakeGoldenRecord([make_m3_product()])


@pytest.fixture
def source_factory() -> Callable[..., SourceProduct]:
    return make_source_product


@pytest.fixture
def m3_factory() -> Callable[..., M3Product]:
    return make_m3_product


@pytest.fixture
def proposal_factory() -> Callable[..., ProductProposal]:
    return make_proposal


@pytest.fixture
def analyzed_factory() -> Callable[..., AnalyzedProduct]:
    return make_analyzed_product


@pytest.fixture
def new_source_product() -> SourceProduct:
    return make_source_product()


@pytest.fixture
def ready_proposal(new_source_product: SourceProduct) -> ProductProposal:
    return make_proposal(new_source_product)


@pytest.fixture
def generator_api():
    return generate_candidate


@pytest.fixture
def candidate_patcher():
    return patch_service_candidates


@pytest.fixture
def assignment_api():
    return assign_item_number


@pytest.fixture
def reservation_api():
    return SimpleNamespace(reserve=reserve, get=get_reservation, is_reserved=is_reserved)


@pytest.fixture
def verification_api():
    return SimpleNamespace(prepare=prepare_product, proposal=prepared_proposal)
