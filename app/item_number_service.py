"""Assign and persistently reserve unique Sæther Codes."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app import item_number_generator, item_number_reservation


DEFAULT_CANDIDATE_ATTEMPTS = 100


def assign_item_number(
    proposal: Any,
    golden_record: Any,
    database_path: str | Path | None = None,
    *,
    verified_generation_prefix: Any,
    max_attempts: int = DEFAULT_CANDIDATE_ATTEMPTS,
) -> str:
    """Assign one persistently reserved code and mutate only ``item_number``.

    ``verified_generation_prefix`` is mandatory and is never inferred from
    ``brand_code`` or MMBUAR. Persistent reservation is the source of truth for
    idempotency and concurrent uniqueness.
    """

    if proposal is None:
        raise ValueError("ProductProposal mangler.")
    source_product = _read(proposal, "source_product")
    if source_product is None:
        raise ValueError("ProductProposal mangler kildeprodukt.")
    if max_attempts <= 0:
        raise ValueError("max_attempts skal være større end nul.")

    prefix = item_number_generator.validate_generation_prefix(
        verified_generation_prefix
    )
    proposal_prefix = _identifier(_read(proposal, "generation_prefix"))
    if proposal_prefix is not None and proposal_prefix != prefix:
        raise ValueError(
            f"Verificeret generation-prefix {prefix} matcher ikke "
            f"forslagets generation-prefix {proposal_prefix}."
        )

    existing_reservation = item_number_reservation.get(
        source_product,
        database_path,
    )
    if existing_reservation is not None:
        reserved_number = item_number_generator.validate_item_number_candidate(
            existing_reservation.item_number,
            prefix,
        )
        proposed_number = _identifier(_read(proposal, "item_number"))
        if proposed_number is not None and proposed_number != reserved_number:
            raise ValueError(
                "ProductProposal har en anden Sæther Code end den persistente "
                "reservation."
            )
        _write_item_number(proposal, reserved_number)
        return reserved_number

    if _identifier(_read(proposal, "item_number")) is not None:
        raise ValueError(
            "ProductProposal har en Sæther Code uden en matchende persistent "
            "reservation."
        )

    attempts = 0
    candidates = item_number_generator.generate_item_number_candidates(
        prefix,
        max_attempts,
    )
    for candidate in candidates:
        attempts += 1
        normalized_candidate = item_number_generator.validate_item_number_candidate(
            candidate,
            prefix,
        )
        if _item_number_exists(golden_record, normalized_candidate):
            continue
        if item_number_reservation.is_reserved(
            normalized_candidate,
            database_path,
        ):
            continue
        try:
            reservation = item_number_reservation.reserve(
                source_product,
                normalized_candidate,
                database_path,
            )
        except item_number_reservation.ReservationConflict:
            # Another writer won the race. The database remains authoritative.
            continue

        reserved_number = item_number_generator.validate_item_number_candidate(
            reservation.item_number,
            prefix,
        )
        _write_item_number(proposal, reserved_number)
        return reserved_number

    raise ValueError(
        "Ingen unik Sæther Code kunne reserveres "
        f"efter {attempts} kandidatforsøg."
    )


def _item_number_exists(golden_record: Any, item_number: str) -> bool:
    if golden_record is None:
        return False
    finder = getattr(golden_record, "find_by_item_number", None)
    if callable(finder):
        value = finder(item_number)
        if value is None:
            return False
        if isinstance(value, (list, tuple, set, frozenset)):
            return bool(value)
        return True
    return any(
        _identifier(_read(product, "mmitno", "item_number", "saether_code"))
        == item_number
        for product in _products(golden_record)
    )


def _products(golden_record: Any) -> Iterable[Any]:
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


def _write_item_number(proposal: Any, item_number: str) -> None:
    if isinstance(proposal, Mapping):
        try:
            proposal["item_number"] = item_number  # type: ignore[index]
            return
        except TypeError as exc:
            raise ValueError(
                "ProductProposal kan ikke opdateres med Sæther Code."
            ) from exc
    setattr(proposal, "item_number", item_number)


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
