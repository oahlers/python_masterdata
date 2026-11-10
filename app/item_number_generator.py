import secrets

from app.golden_record import GoldenRecord
from app.brand_rules import resolve_brand_rule


SUFFIX_LENGTH = 8
MAX_ATTEMPTS = 100


def validate_generation_prefix(
    generation_prefix: str,
) -> str:
    """
    Et generation-prefix skal bestå af præcis tre cifre.

    Bemærk:
    Dette er generation-prefixet, ikke nødvendigvis MMBUAR.
    """

    prefix = str(generation_prefix).strip()

    if len(prefix) != 3 or not prefix.isdigit():
        raise ValueError(
            "Generation-prefix skal bestå af præcis tre cifre."
        )

    return prefix


def generate_suffix() -> str:
    """
    Genererer præcis otte tilfældige cifre.
    """

    return f"{secrets.randbelow(100_000_000):08d}"


def item_number_exists(
    item_number: str,
    golden_record: GoldenRecord,
    reserved_numbers: set[str] | None = None,
) -> bool:
    """
    Kontrollerer både Golden Record og numre,
    som allerede er reserveret i den aktuelle import.
    """

    if golden_record.find_by_item_number(item_number) is not None:
        return True

    if reserved_numbers and item_number in reserved_numbers:
        return True

    return False


def generate_item_number(
    generation_prefix: str,
    golden_record: GoldenRecord,
    reserved_numbers: set[str] | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> str:
    """
    Genererer et nyt globalt unikt MMITNO.

    Format:
        3-cifret generation-prefix
        +
        8 tilfældige cifre

    Eksempel:
        128 + 12345678
        = 12812345678
    """

    prefix = validate_generation_prefix(
        generation_prefix
    )

    if reserved_numbers is None:
        reserved_numbers = set()

    for _ in range(max_attempts):
        item_number = (
            prefix
            + generate_suffix()
        )

        if item_number_exists(
            item_number,
            golden_record,
            reserved_numbers,
        ):
            continue

        reserved_numbers.add(item_number)

        return item_number

    raise RuntimeError(
        f"Kunne ikke generere et ledigt MMITNO for "
        f"generation-prefix {prefix} efter "
        f"{max_attempts} forsøg."
    )

def generate_item_number_for_brand(
    brand_code: str,
    golden_record: GoldenRecord,
    reserved_numbers: set[str] | None = None,
) -> str:
    """
    Genererer MMITNO ud fra brandets verificerede
    generation-prefix.

    Prefix vælges aldrig direkte fra MMBUAR.
    Det skal først godkendes af brand_rules.
    """

    resolution = resolve_brand_rule(
        brand_code=brand_code,
        products=golden_record.products,
    )

    if resolution.rule is None:
        observed = [
            prefix
            for prefix, _ in resolution.prefix_counts
        ]

        raise ValueError(
            f"Brand {brand_code} har ikke et sikkert "
            f"generation-prefix. "
            f"Status: {resolution.status}. "
            f"Observerede prefixes: {observed}"
        )

    return generate_item_number(
        generation_prefix=(
            resolution.rule.generation_prefix
        ),
        golden_record=golden_record,
        reserved_numbers=reserved_numbers,
    )