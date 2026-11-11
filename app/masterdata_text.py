"""Documented M3 text resolution, kept separate from classification.

The resolver never invents or truncates text.  It records where each value came
from and distinguishes a missing documented value from a field that does not
apply to the resolved item type.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Callable


DOCUMENTED = "documented"
MISSING_DOCUMENTED_SOURCE = "missing_documented_source"
NOT_APPLICABLE = "not_applicable"
AWAITING_ITEM_TYPE = "awaiting_item_type"
REVIEW_REQUIRED_LENGTH = "review_required_length"


@dataclass(frozen=True, slots=True)
class M3TextResolution:
    m3_name: str | None
    m3_name_status: str
    m3_name_source: str | None
    m3_name_reason: str | None

    m3_description: str | None
    m3_description_status: str
    m3_description_source: str | None
    m3_description_reason: str | None

    receipt_text: str | None
    receipt_text_status: str
    receipt_text_source: str | None
    receipt_text_reason: str | None
    receipt_text_required: bool

    review_fields: tuple[str, ...] = ()


def resolve_m3_text(
    proposal: Any,
    source_product: Any,
    strongest_rows: Iterable[Any] = (),
    *,
    item_type: str | None = None,
) -> M3TextResolution:
    """Resolve Line 1, Line 2, and receipt text from documented sources.

    Precedence is explicit reviewed value, supplier value, then safe direct M3
    evidence.  Item type 12 is a tester, so receipt text is deliberately blank
    and marked ``not_applicable`` even if a retail sibling has receipt text.
    Item type 00 is a sales item and therefore requires receipt text.
    """

    rows = tuple(strongest_rows)
    review_values = _review_values(proposal, source_product)
    resolved_item_type = _identifier_or_none(
        _coalesce(
            item_type,
            _read(review_values, "item_type", "mmity"),
            _read(proposal, "item_type", "mmity"),
        )
    )
    review: set[str] = set()

    name, name_source = _first_documented_text(
        (
            (review_values, ("m3_name", "line_1"), "reviewed_value"),
            (
                source_product,
                ("m3_name", "line_1", "product_name", "name"),
                "supplier_product_name",
            ),
        )
    )
    if name is None and _safe_text_evidence(rows):
        name = _unique_text(rows, lambda row: _read(row, "mmitds"))
        if name is not None:
            name_source = "golden_record_sibling"
    name, name_status, name_reason = _bounded(
        name,
        30,
        uppercase=True,
        missing_reason="No documented Line 1 source was found.",
    )
    if name is None:
        review.add("m3_name")

    description, description_source = _first_documented_text(
        (
            (
                review_values,
                ("m3_description", "line_2"),
                "reviewed_value",
            ),
            (
                source_product,
                ("m3_description", "line_2"),
                "supplier_line_2",
            ),
        )
    )
    if description is None and _safe_text_evidence(rows):
        description = _unique_text(rows, lambda row: _read(row, "mmfuds"))
        if description is not None:
            description_source = "golden_record_sibling"
    description, description_status, description_reason = _bounded(
        description,
        60,
        missing_reason="No documented Line 2 source was found.",
    )
    if description is None:
        review.add("m3_description")

    receipt_required = resolved_item_type == "00"
    if resolved_item_type is None:
        receipt = None
        receipt_source = "item_type_rule"
        receipt_status = AWAITING_ITEM_TYPE
        receipt_reason = (
            "Receipt-text applicability cannot be determined until item type "
            "is resolved."
        )
    elif resolved_item_type == "12":
        receipt = None
        receipt_source = "item_type_rule"
        receipt_status = NOT_APPLICABLE
        receipt_reason = "Item type 12 is a tester."
    else:
        receipt, receipt_source = _first_documented_text(
            (
                (
                    review_values,
                    ("receipt_text", "till_receipt_text"),
                    "reviewed_value",
                ),
                (
                    source_product,
                    (
                        "receipt_text",
                        "till_receipt_text",
                        "short_receipt_text",
                    ),
                    "supplier_receipt_text",
                ),
            )
        )
        if receipt is None and _safe_text_evidence(rows):
            receipt = _unique_text(
                rows,
                lambda row: _read(
                    row,
                    "receipt_text",
                    "till_receipt_text",
                    "short_receipt_text",
                    "mmreceipt",
                ),
            )
            if receipt is not None:
                receipt_source = "golden_record_sibling"
        receipt, receipt_status, receipt_reason = _bounded(
            receipt,
            20,
            missing_reason=(
                "Receipt text is required for sales item type 00."
                if receipt_required
                else "No documented receipt-text source was found."
            ),
        )
        if receipt is None:
            review.add("receipt_text")

    return M3TextResolution(
        m3_name=name,
        m3_name_status=name_status,
        m3_name_source=name_source if name is not None else None,
        m3_name_reason=name_reason,
        m3_description=description,
        m3_description_status=description_status,
        m3_description_source=(
            description_source if description is not None else None
        ),
        m3_description_reason=description_reason,
        receipt_text=receipt,
        receipt_text_status=receipt_status,
        receipt_text_source=receipt_source,
        receipt_text_reason=receipt_reason,
        receipt_text_required=receipt_required,
        review_fields=tuple(sorted(review)),
    )


def _bounded(
    value: str | None,
    limit: int,
    *,
    uppercase: bool = False,
    missing_reason: str,
) -> tuple[str | None, str, str | None]:
    if value is None:
        return None, MISSING_DOCUMENTED_SOURCE, missing_reason
    normalized = " ".join(value.split())
    if uppercase:
        normalized = normalized.upper()
    if len(normalized) > limit:
        return (
            None,
            REVIEW_REQUIRED_LENGTH,
            f"Documented text exceeds the {limit}-character limit; it was not truncated.",
        )
    return normalized, DOCUMENTED, None


def _first_documented_text(
    candidates: Iterable[tuple[Any, tuple[str, ...], str]],
) -> tuple[str | None, str | None]:
    for obj, names, source in candidates:
        value = _text_or_none(_read(obj, *names))
        if value is not None:
            return value, source
    return None, None


def _safe_text_evidence(rows: tuple[Any, ...]) -> bool:
    if not rows:
        return False
    return len(rows) == 1 or all(
        bool(_read(row, "direct_sibling", "exact_variant")) for row in rows
    )


def _unique_text(
    rows: Iterable[Any],
    getter: Callable[[Any], Any],
) -> str | None:
    values: dict[str, str] = {}
    for row in rows:
        value = _text_or_none(getter(row))
        if value is None:
            continue
        values.setdefault(value.casefold(), value)
    if len(values) != 1:
        return None
    return next(iter(values.values()))


def _review_values(*objects: Any) -> Mapping[str, Any]:
    merged: dict[str, Any] = {}
    for obj in objects:
        value = _read(obj, "masterdata_review", "masterdata_overrides")
        if isinstance(value, Mapping):
            merged.update(value)
    return merged


def _read(obj: Any, *names: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        folded = {str(key).casefold(): value for key, value in obj.items()}
        for name in names:
            value = folded.get(name.casefold())
            if value is not None:
                return value
        nested = folded.get("raw_data")
        if isinstance(nested, Mapping) and nested is not obj:
            return _read(nested, *names)
        return None
    for name in names:
        for candidate in (name, name.lower(), name.upper()):
            if hasattr(obj, candidate):
                value = getattr(obj, candidate)
                if value is not None:
                    return value
    nested = getattr(obj, "raw_data", None)
    if isinstance(nested, Mapping):
        return _read(nested, *names)
    return None


def _coalesce(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _identifier_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    result = str(value).strip()
    return result or None


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    result = " ".join(str(value).split())
    return result or None
