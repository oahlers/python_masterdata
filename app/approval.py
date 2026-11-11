"""Tuple-safe final approval gate for the MASTERDATA MVP.

Approval revalidates the mutable external facts that can change after SKU
preparation: the persistent reservation and Golden Record uniqueness.  Review
collections are normalized without mutation, so tuples remain safe.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app import item_number_reservation


@dataclass(slots=True)
class ApprovedProduct:
    source_product: Any | None = None
    proposal: Any | None = None
    status: str = "APPROVED"
    approved_at: str | None = None
    approval_source: str = "user"
    approved: bool = True


def validate_proposal_for_approval(
    *,
    proposal: Any,
    golden_record: Any,
    database_path: str | Path | None = None,
    source_product: Any | None = None,
) -> tuple[str, ...]:
    """Return every approval blocker without mutating ``proposal``."""

    errors: list[str] = []
    if proposal is None:
        return ("Produktet mangler ProductProposal.",)

    resolved_source = source_product or _read(proposal, "source_product", "source")
    item_number = _identifier(_read(proposal, "item_number", "mmitno"))

    reservation = None
    if item_number is None:
        errors.append("Sæther Code skal være persistent reserveret før godkendelse.")
    elif resolved_source is None:
        errors.append("Kildeproduktet mangler; persistent reservation kan ikke valideres.")
    else:
        try:
            reservation = item_number_reservation.get(resolved_source, database_path)
        except (TypeError, ValueError) as exc:
            errors.append(f"Persistent reservation kan ikke valideres: {exc}")
        if reservation is None:
            errors.append(
                "Sæther Code er ikke persistent reserveret til dette produkt."
            )
        elif _identifier(reservation.item_number) != item_number:
            errors.append(
                "Forslagets Sæther Code matcher ikke produktets persistente "
                f"reservation ({reservation.item_number})."
            )

    unresolved = _unresolved_review_fields(proposal)
    # ``item_number`` is resolved only by a matching persistent reservation.
    if reservation is not None and _identifier(reservation.item_number) == item_number:
        unresolved = tuple(field for field in unresolved if field != "item_number")

    if unresolved:
        errors.append(
            "Produktet kræver review af: " + ", ".join(unresolved) + "."
        )

    proposal_status = _identifier(_read(proposal, "status"))
    if proposal_status and proposal_status.upper() in {
        "REVIEW",
        "NEEDS_REVIEW",
        "BLOCKED",
        "AMBIGUOUS",
        "IDENTIFIER_CONFLICT",
    }:
        errors.append(f"Produktstatus {proposal_status} kræver review før approval.")

    if item_number is not None:
        item_matches = _find_by_item_number(golden_record, item_number)
        if item_matches:
            errors.append(
                f"Sæther Code {item_number} findes allerede i Golden Record."
            )

    incoming_ean = _identifier(_read(resolved_source, "ean", "gtin"))
    if incoming_ean is not None:
        ean_matches = _find_by_ean(golden_record, incoming_ean)
        if ean_matches:
            errors.append(f"EAN {incoming_ean} findes allerede i Golden Record.")

    return tuple(dict.fromkeys(errors))


def approve_product(
    *,
    proposal: Any,
    golden_record: Any,
    confirmed: bool,
    database_path: str | Path | None = None,
    source_product: Any | None = None,
    approval_source: str = "user",
) -> ApprovedProduct:
    """Revalidate and create an immutable-in-practice approval snapshot."""

    if confirmed is not True:
        raise ValueError("Approval kræver eksplicit brugergodkendelse.")

    errors = validate_proposal_for_approval(
        proposal=proposal,
        golden_record=golden_record,
        database_path=database_path,
        source_product=source_product,
    )
    if errors:
        raise ValueError("Approval blokeret: " + " ".join(errors))

    resolved_source = source_product or _read(proposal, "source_product", "source")
    return ApprovedProduct(
        source_product=resolved_source,
        proposal=proposal,
        approved_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        approval_source=approval_source,
    )


def _unresolved_review_fields(proposal: Any) -> tuple[str, ...]:
    values = _read(proposal, "needs_review", "review_fields") or ()
    if isinstance(values, str):
        values = (values,)
    return tuple(
        dict.fromkeys(
            text
            for value in values
            if (text := str(value).strip())
        )
    )


def _find_by_item_number(golden_record: Any, item_number: str) -> list[Any]:
    if golden_record is None:
        return []
    finder = getattr(golden_record, "find_by_item_number", None)
    if callable(finder):
        return _as_list(finder(item_number))
    return [
        product
        for product in _products(golden_record)
        if _identifier(_read(product, "mmitno", "item_number", "saether_code"))
        == item_number
    ]


def _find_by_ean(golden_record: Any, ean: str) -> list[Any]:
    if golden_record is None:
        return []
    finder = getattr(golden_record, "find_by_ean", None)
    if callable(finder):
        return _as_list(finder(ean))
    return [
        product
        for product in _products(golden_record)
        if _identifier(_read(product, "ean", "gtin")) == ean
    ]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        return [item for item in value if item is not None]
    return [value]


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
