"""Prepare READY analyzed products for review and approval."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.import_analyzer import AnalyzedProduct
from app.item_number_service import assign_item_number
from app.product_resolver import NEW_PRODUCT


@dataclass(slots=True)
class VerificationItem:
    product_key: str
    product_code: str | None = None
    ean: str | None = None
    product_name: str | None = None
    status: str = "PREPARED"
    item_number: str | None = None
    incoming_saether_code: str | None = None
    mmstat: str | None = None
    item_type: str | None = None
    brand_code: str | None = None
    brand_name: str | None = None
    item_group: str | None = None
    item_class: str | None = None
    product_line: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VerificationBatch:
    analysis_id: str
    requested_count: int = 0
    prepared_count: int = 0
    blocked_count: int = 0
    can_continue: bool = True
    items: list[VerificationItem] = field(default_factory=list)


def prepare_for_verification(
    analyzed_product: AnalyzedProduct,
    golden_record: Any,
    database_path: str | Path | None = None,
) -> VerificationItem:
    """Return one PREPARED or BLOCKED item from an authoritative analysis row."""

    if not isinstance(analyzed_product, AnalyzedProduct):
        return _blocked(
            None,
            None,
            "Verification kræver et AnalyzedProduct som autoritativt input.",
        )

    source = analyzed_product.source_product
    proposal = analyzed_product.proposal

    if analyzed_product.status != "READY":
        return _blocked(
            source,
            proposal,
            "Kun et produkt med workflow-status READY kan forberedes.",
        )

    if analyzed_product.product_resolution.status != NEW_PRODUCT:
        return _blocked(
            source,
            proposal,
            "Kun identity-resultatet NEW_PRODUCT kan få en ny Sæther Code.",
        )

    if analyzed_product.existing_products:
        return _blocked(
            source,
            proposal,
            "Et eksisterende produkt kan ikke få en ny Sæther Code.",
        )

    if proposal is None:
        return _blocked(
            source,
            None,
            "AnalyzedProduct mangler ProductProposal.",
        )

    blockers = _review_blockers(proposal)
    if blockers:
        return _blocked(
            source,
            proposal,
            "Produktet kræver review af: " + ", ".join(blockers) + ".",
        )

    generation_prefix = _identifier(_read(proposal, "generation_prefix"))
    if generation_prefix is None:
        return _blocked(
            source,
            proposal,
            "ProductProposal mangler et verificeret generation-prefix.",
        )

    try:
        item_number = assign_item_number(
            proposal,
            golden_record,
            database_path,
            verified_generation_prefix=generation_prefix,
        )
    except (TypeError, ValueError) as exc:
        return _blocked(source, proposal, str(exc))

    return _verification_item(
        source,
        proposal,
        status="PREPARED",
        item_number=item_number,
    )


def prepare_verification_batch(
    analysis_id: str,
    products: Iterable[AnalyzedProduct],
    golden_record: Any,
    database_path: str | Path | None = None,
) -> VerificationBatch:
    """Prepare a batch while retaining blocked rows for the UI."""

    product_list = list(products)
    batch = VerificationBatch(
        analysis_id=str(analysis_id),
        requested_count=len(product_list),
    )
    for analyzed_product in product_list:
        item = prepare_for_verification(
            analyzed_product,
            golden_record,
            database_path,
        )
        batch.items.append(item)
        if item.status == "PREPARED":
            batch.prepared_count += 1
        else:
            batch.blocked_count += 1
    batch.can_continue = batch.prepared_count > 0 and batch.blocked_count == 0
    return batch


def _blocked(source: Any, proposal: Any, error: str) -> VerificationItem:
    return _verification_item(
        source,
        proposal,
        status="BLOCKED",
        errors=[error],
    )


def _verification_item(
    source: Any,
    proposal: Any,
    *,
    status: str,
    item_number: str | None = None,
    errors: list[str] | None = None,
) -> VerificationItem:
    product_code = _identifier(_read(source, "product_code", "reference"))
    ean = _identifier(_read(source, "ean", "gtin"))
    return VerificationItem(
        product_key=ean or product_code or "unknown",
        product_code=product_code,
        ean=ean,
        product_name=_identifier(_read(source, "product_name", "name")),
        status=status,
        item_number=item_number
        or _identifier(_read(proposal, "item_number", "mmitno")),
        incoming_saether_code=_identifier(
            _read(source, "saether_code", "item_number", "mmitno")
        ),
        mmstat=_identifier(_read(proposal, "mmstat")),
        item_type=_identifier(_read(proposal, "item_type", "mmity")),
        brand_code=_identifier(_read(proposal, "brand_code")),
        brand_name=_identifier(_read(proposal, "brand_name")),
        item_group=_identifier(_read(proposal, "item_group")),
        item_class=_identifier(_read(proposal, "item_class")),
        product_line=_identifier(_read(proposal, "product_line")),
        errors=list(errors or ()),
    )


def _review_blockers(proposal: Any) -> tuple[str, ...]:
    review_fields = _read(proposal, "needs_review", "review_fields") or ()
    if isinstance(review_fields, str):
        review_fields = (review_fields,)

    blockers = [
        text
        for value in review_fields
        if (text := str(value).strip()) and text != "item_number"
    ]
    required_fields = (
        "brand_code",
        "generation_prefix",
        "item_group",
        "item_class",
        "item_type",
        "product_line",
    )
    blockers.extend(
        field_name
        for field_name in required_fields
        if _identifier(_read(proposal, field_name)) is None
    )
    return tuple(dict.fromkeys(blockers))


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
