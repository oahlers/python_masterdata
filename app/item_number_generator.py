"""Pure validation and generation of Sæther Code candidates."""
from __future__ import annotations

import secrets
from collections.abc import Iterator
from typing import Any


PREFIX_LENGTH = 3
SUFFIX_LENGTH = 8
ITEM_NUMBER_LENGTH = PREFIX_LENGTH + SUFFIX_LENGTH
DEFAULT_CANDIDATE_COUNT = 100


def validate_generation_prefix(generation_prefix: Any) -> str:
    """Return a normalized prefix or reject anything except exactly three digits."""

    if generation_prefix is None:
        raise ValueError("Generation-prefix skal bestå af præcis tre cifre.")
    prefix = str(generation_prefix).strip()
    if len(prefix) != PREFIX_LENGTH or not prefix.isdigit():
        raise ValueError("Generation-prefix skal bestå af præcis tre cifre.")
    return prefix


def generate_suffix() -> str:
    """Generate exactly eight random decimal digits, preserving leading zeroes."""

    return f"{secrets.randbelow(10**SUFFIX_LENGTH):0{SUFFIX_LENGTH}d}"


def validate_item_number_candidate(
    candidate: Any,
    generation_prefix: Any,
) -> str:
    """Validate an eleven-digit candidate against an explicit verified prefix."""

    prefix = validate_generation_prefix(generation_prefix)
    if candidate is None:
        raise ValueError("Sæther Code-kandidat mangler.")
    value = str(candidate).strip()
    if (
        len(value) != ITEM_NUMBER_LENGTH
        or not value.isdigit()
        or not value.startswith(prefix)
    ):
        raise ValueError(
            "Sæther Code-kandidat skal bestå af generation-prefixet "
            "efterfulgt af præcis otte cifre."
        )
    return value


def generate_item_number(generation_prefix: Any) -> str:
    """Generate one format-valid candidate; uniqueness is a service responsibility."""

    prefix = validate_generation_prefix(generation_prefix)
    return prefix + generate_suffix()


def generate_item_number_candidates(
    generation_prefix: Any,
    count: int = DEFAULT_CANDIDATE_COUNT,
) -> Iterator[str]:
    """Yield a bounded sequence of format-valid candidates."""

    prefix = validate_generation_prefix(generation_prefix)
    if count < 0:
        raise ValueError("Antal kandidater må ikke være negativt.")
    for _ in range(count):
        yield prefix + generate_suffix()
