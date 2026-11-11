"""Resolve an imported source product against the Golden Record."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


NEW_PRODUCT = "NEW_PRODUCT"
EXISTING_PRODUCT = "EXISTING_PRODUCT"
IDENTIFIER_CONFLICT = "IDENTIFIER_CONFLICT"
AMBIGUOUS = "AMBIGUOUS"
RESOLUTION_STATUSES = frozenset(
    {NEW_PRODUCT, EXISTING_PRODUCT, IDENTIFIER_CONFLICT, AMBIGUOUS}
)


@dataclass(slots=True)
class ProductResolution:
    status: str
    source_product: Any
    existing_products: list[Any] = field(default_factory=list)
    message: str = ""

    def __post_init__(self) -> None:
        if self.status not in RESOLUTION_STATUSES:
            raise ValueError(f"Ukendt ProductResolution-status: {self.status}")

    @property
    def existing_product(self) -> Any | None:
        return self.existing_products[0] if len(self.existing_products) == 1 else None


class ProductResolver:
    def __init__(self, golden_record: Any) -> None:
        self.golden_record = golden_record

    def resolve(self, source_product: Any) -> ProductResolution:
        incoming_item_number = _identifier(
            _read(source_product, "saether_code", "item_number", "mmitno")
        )
        incoming_ean = _identifier(_read(source_product, "ean", "gtin"))

        item_number_matches = self._find_by_item_number(incoming_item_number)
        ean_matches = self._find_by_ean(incoming_ean)
        all_matches = _deduplicate(item_number_matches + ean_matches)

        if len(item_number_matches) > 1 or len(ean_matches) > 1:
            return ProductResolution(
                status=AMBIGUOUS,
                source_product=source_product,
                existing_products=all_matches,
                message=(
                    "Identifikatoren matcher flere produkter i Golden Record "
                    "og kræver derfor manuel kontrol."
                ),
            )

        item_number_match = item_number_matches[0] if item_number_matches else None
        ean_match = ean_matches[0] if ean_matches else None

        if item_number_match is not None:
            record_ean = _identifier(_read(item_number_match, "ean", "gtin"))
            if incoming_ean and record_ean and incoming_ean != record_ean:
                return ProductResolution(
                    status=IDENTIFIER_CONFLICT,
                    source_product=source_product,
                    existing_products=all_matches,
                    message=(
                        "Indgående Sæther Code findes i Golden Record med en "
                        "anden EAN."
                    ),
                )
            if ean_match is not None and not _same_record(
                item_number_match,
                ean_match,
            ):
                return ProductResolution(
                    status=IDENTIFIER_CONFLICT,
                    source_product=source_product,
                    existing_products=all_matches,
                    message=(
                        "Sæther Code og EAN peger på forskellige produkter i "
                        "Golden Record."
                    ),
                )
            return ProductResolution(
                status=EXISTING_PRODUCT,
                source_product=source_product,
                existing_products=[item_number_match],
                message="Produktet findes allerede i Golden Record.",
            )

        if ean_match is not None:
            record_item_number = _identifier(
                _read(ean_match, "mmitno", "item_number", "saether_code")
            )
            if (
                incoming_item_number
                and record_item_number
                and incoming_item_number != record_item_number
            ):
                return ProductResolution(
                    status=IDENTIFIER_CONFLICT,
                    source_product=source_product,
                    existing_products=[ean_match],
                    message=(
                        "Indgående EAN findes i Golden Record med en anden "
                        "Sæther Code."
                    ),
                )
            return ProductResolution(
                status=EXISTING_PRODUCT,
                source_product=source_product,
                existing_products=[ean_match],
                message="Produktets EAN findes allerede i Golden Record.",
            )

        return ProductResolution(
            status=NEW_PRODUCT,
            source_product=source_product,
            message="Produktet findes ikke i Golden Record.",
        )

    def _find_by_item_number(self, item_number: str | None) -> list[Any]:
        if item_number is None or self.golden_record is None:
            return []
        finder = getattr(self.golden_record, "find_by_item_number", None)
        if callable(finder):
            return _as_product_list(finder(item_number))
        return [
            product
            for product in _products(self.golden_record)
            if _identifier(_read(product, "mmitno", "item_number", "saether_code"))
            == item_number
        ]

    def _find_by_ean(self, ean: str | None) -> list[Any]:
        if ean is None or self.golden_record is None:
            return []
        finder = getattr(self.golden_record, "find_by_ean", None)
        if callable(finder):
            return _as_product_list(finder(ean))
        return [
            product
            for product in _products(self.golden_record)
            if _identifier(_read(product, "ean", "gtin")) == ean
        ]


def resolve_product(source_product: Any, golden_record: Any) -> ProductResolution:
    return ProductResolver(golden_record).resolve(source_product)


def _as_product_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        return [value]
    if isinstance(value, Iterable):
        return [product for product in value if product is not None]
    return [value]


def _deduplicate(products: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[tuple[str | None, str | None, int]] = set()
    for product in products:
        item_number = _identifier(
            _read(product, "mmitno", "item_number", "saether_code")
        )
        ean = _identifier(_read(product, "ean", "gtin"))
        key = (item_number, ean, 0 if item_number or ean else id(product))
        if key not in seen:
            seen.add(key)
            result.append(product)
    return result


def _same_record(left: Any, right: Any) -> bool:
    if left is right:
        return True
    left_item = _identifier(_read(left, "mmitno", "item_number", "saether_code"))
    right_item = _identifier(_read(right, "mmitno", "item_number", "saether_code"))
    if left_item and right_item:
        return left_item == right_item
    left_ean = _identifier(_read(left, "ean", "gtin"))
    right_ean = _identifier(_read(right, "ean", "gtin"))
    return bool(left_ean and right_ean and left_ean == right_ean)


def _products(golden_record: Any) -> tuple[Any, ...]:
    if golden_record is None:
        return ()
    for name in ("products", "records", "items"):
        value = _read(golden_record, name)
        if value is not None:
            return tuple(value)
    if isinstance(golden_record, Mapping):
        return tuple(golden_record.values())
    try:
        return tuple(golden_record)
    except TypeError:
        return ()


def _read(obj: Any, *names: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        folded = {str(key).casefold(): value for key, value in obj.items()}
        for name in names:
            if name.casefold() in folded:
                return folded[name.casefold()]
        return None
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _identifier(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None
