from collections import Counter
from dataclasses import dataclass

from app.brand_rule_store import get_override
from app.models import M3Product


MIN_REFERENCE_PRODUCTS = 20
MIN_PREFIX_CONFIDENCE = 0.99


@dataclass(frozen=True)
class BrandRule:
    brand_code: str
    brand_name: str
    generation_prefix: str
    source: str

    reference_count: int = 0
    matching_count: int = 0
    confidence: float = 0.0


@dataclass(frozen=True)
class BrandRuleResolution:
    status: str

    rule: BrandRule | None = None

    brand_code: str | None = None
    brand_name: str | None = None

    reference_count: int = 0
    matching_count: int = 0
    confidence: float = 0.0

    prefix_counts: tuple[tuple[str, int], ...] = ()

    message: str = ""


# ---------------------------------------------------------
# EKSPLICIT DOKUMENTEREDE OVERRIDES
# ---------------------------------------------------------
#
# Brug denne tabel til regler, som er dokumenteret uden for
# Golden Record og ikke kommer fra brugerens gemte valg.
#
# Eksempel:
#
# "123": BrandRule(
#     brand_code="123",
#     brand_name="VAN GILS",
#     generation_prefix="123",
#     source="documented_override",
# ),
#
# VAN GILS er ikke indsat nu. Golden Record viser både
# prefix 123 og 197, så brugeren skal vælge det korrekte.
#

EXPLICIT_BRAND_RULES: dict[str, BrandRule] = {}


def clean_value(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    cleaned = str(value).strip()

    return cleaned or None


def is_valid_generation_prefix(
    value: str | None,
) -> bool:
    if value is None:
        return False

    return (
        len(value) == 3
        and value.isdigit()
    )


def get_item_number_prefix(
    item_number: str | None,
) -> str | None:
    """
    Returnerer de første tre tegn af MMITNO.

    Prefixet valideres ikke her. Dermed kan analysen
    også opdage historiske anomalier som TES og M53.
    """

    item_number = clean_value(item_number)

    if not item_number:
        return None

    if len(item_number) < 3:
        return None

    return item_number[:3]


def get_reference_products_for_brand(
    brand_code: str,
    products: list[M3Product],
) -> list[M3Product]:
    """
    Finder MMSTAT 20-referenceprodukter for ét MMBUAR.
    """

    normalized_brand_code = clean_value(
        brand_code
    )

    if not normalized_brand_code:
        return []

    return [
        product
        for product in products
        if (
            clean_value(product.mmbuar)
            == normalized_brand_code
            and clean_value(product.mmstat)
            == "20"
            and get_item_number_prefix(
                product.mmitno
            )
            is not None
        )
    ]


def resolve_brand_name(
    products: list[M3Product],
    fallback_brand_code: str,
) -> str:
    """
    Finder det mest almindelige MMBUARTX40-navn
    blandt brandets referenceprodukter.
    """

    names = Counter(
        clean_value(product.mmbuartx40)
        for product in products
        if clean_value(product.mmbuartx40)
    )

    if not names:
        return fallback_brand_code

    return names.most_common(1)[0][0]


def get_observed_prefixes(
    brand_code: str,
    products: list[M3Product],
) -> tuple[tuple[str, int], ...]:
    """
    Returnerer alle observerede MMITNO-prefixes for brandets
    MMSTAT 20-referenceprodukter.
    """

    references = get_reference_products_for_brand(
        brand_code,
        products,
    )

    prefixes = Counter(
        get_item_number_prefix(product.mmitno)
        for product in references
        if get_item_number_prefix(product.mmitno)
    )

    return tuple(
        prefixes.most_common()
    )


def resolve_dynamic_brand_rule(
    brand_code: str,
    products: list[M3Product],
    minimum_reference_products: int = MIN_REFERENCE_PRODUCTS,
    minimum_confidence: float = MIN_PREFIX_CONFIDENCE,
) -> BrandRuleResolution:
    """
    Udleder generation-prefix fra Golden Record.

    En regel accepteres kun, hvis:

    1. Brandet har mindst det krævede antal MMSTAT 20-varer.
    2. Det dominerende prefix består af præcis tre cifre.
    3. Den krævede andel af referencevarerne bruger prefixet.

    MMBUAR bruges som brandidentitet, men bruges ikke
    automatisk som generation-prefix.
    """

    normalized_brand_code = clean_value(
        brand_code
    )

    if not normalized_brand_code:
        return BrandRuleResolution(
            status="NOT_FOUND",
            message="Brandkoden er tom eller ugyldig.",
        )

    references = get_reference_products_for_brand(
        normalized_brand_code,
        products,
    )

    if not references:
        return BrandRuleResolution(
            status="NOT_FOUND",
            brand_code=normalized_brand_code,
            message=(
                "Ingen MMSTAT 20-referenceprodukter "
                "blev fundet for brandet."
            ),
        )

    brand_name = resolve_brand_name(
        references,
        normalized_brand_code,
    )

    prefix_counts = get_observed_prefixes(
        normalized_brand_code,
        products,
    )

    reference_count = sum(
        count
        for _, count in prefix_counts
    )

    if reference_count < minimum_reference_products:
        return BrandRuleResolution(
            status="INSUFFICIENT_DATA",
            brand_code=normalized_brand_code,
            brand_name=brand_name,
            reference_count=reference_count,
            prefix_counts=prefix_counts,
            message=(
                f"Brandet har kun {reference_count} "
                "referencevarer. "
                f"Minimum er {minimum_reference_products}."
            ),
        )

    generation_prefix, matching_count = (
        prefix_counts[0]
    )

    confidence = (
        matching_count
        / reference_count
    )

    if not is_valid_generation_prefix(
        generation_prefix
    ):
        return BrandRuleResolution(
            status="INVALID_PREFIX",
            brand_code=normalized_brand_code,
            brand_name=brand_name,
            reference_count=reference_count,
            matching_count=matching_count,
            confidence=confidence,
            prefix_counts=prefix_counts,
            message=(
                f"Det dominerende prefix "
                f"{generation_prefix!r} er ikke "
                "et gyldigt trecifret generation-prefix."
            ),
        )

    if confidence < minimum_confidence:
        return BrandRuleResolution(
            status="AMBIGUOUS",
            brand_code=normalized_brand_code,
            brand_name=brand_name,
            reference_count=reference_count,
            matching_count=matching_count,
            confidence=confidence,
            prefix_counts=prefix_counts,
            message=(
                f"Prefix {generation_prefix} bruges af "
                f"{matching_count} af "
                f"{reference_count} referencevarer "
                f"({confidence:.2%}). "
                f"Kravet er {minimum_confidence:.2%}."
            ),
        )

    rule = BrandRule(
        brand_code=normalized_brand_code,
        brand_name=brand_name,
        generation_prefix=generation_prefix,
        source="golden_record_consensus",
        reference_count=reference_count,
        matching_count=matching_count,
        confidence=confidence,
    )

    return BrandRuleResolution(
        status="VERIFIED_DATA",
        rule=rule,
        brand_code=normalized_brand_code,
        brand_name=brand_name,
        reference_count=reference_count,
        matching_count=matching_count,
        confidence=confidence,
        prefix_counts=prefix_counts,
        message=(
            f"Generation-prefix {generation_prefix} "
            f"er verificeret af {matching_count} ud af "
            f"{reference_count} MMSTAT 20-varenumre "
            f"({confidence:.2%})."
        ),
    )


def resolve_brand_rule(
    brand_code: str | None,
    products: list[M3Product],
    minimum_reference_products: int = MIN_REFERENCE_PRODUCTS,
    minimum_confidence: float = MIN_PREFIX_CONFIDENCE,
) -> BrandRuleResolution:
    """
    Finder generation-reglen for et brand.

    Prioritet:

    1. Tidligere brugergodkendt valg.
    2. Eksplicit dokumenteret override.
    3. Dynamisk Golden Record-konsensus.
    4. Ellers manuel review.
    """

    normalized_brand_code = clean_value(
        brand_code
    )

    if not normalized_brand_code:
        return BrandRuleResolution(
            status="NOT_FOUND",
            message="Brandkoden er tom eller ugyldig.",
        )

    # ---------------------------------------------------------
    # BRUGERGODKENDT OVERRIDE
    # ---------------------------------------------------------

    user_override = get_override(
        normalized_brand_code
    )

    if user_override is not None:
        generation_prefix = clean_value(
            user_override.get(
                "generation_prefix"
            )
        )

        brand_name = clean_value(
            user_override.get(
                "brand_name"
            )
        )

        if not is_valid_generation_prefix(
            generation_prefix
        ):
            return BrandRuleResolution(
                status="INVALID_PREFIX",
                brand_code=normalized_brand_code,
                brand_name=brand_name,
                message=(
                    "Den gemte brugerregel indeholder "
                    "et ugyldigt generation-prefix."
                ),
            )

        rule = BrandRule(
            brand_code=normalized_brand_code,
            brand_name=(
                brand_name
                or normalized_brand_code
            ),
            generation_prefix=generation_prefix,
            source="user_approved_override",
        )

        return BrandRuleResolution(
            status="VERIFIED_USER_OVERRIDE",
            rule=rule,
            brand_code=rule.brand_code,
            brand_name=rule.brand_name,
            message=(
                f"Generation-prefix "
                f"{generation_prefix} kommer fra "
                "en tidligere brugergodkendt regel."
            ),
        )

    # ---------------------------------------------------------
    # DOKUMENTERET OVERRIDE
    # ---------------------------------------------------------

    explicit_rule = EXPLICIT_BRAND_RULES.get(
        normalized_brand_code
    )

    if explicit_rule is not None:
        if not is_valid_generation_prefix(
            explicit_rule.generation_prefix
        ):
            return BrandRuleResolution(
                status="INVALID_PREFIX",
                brand_code=normalized_brand_code,
                brand_name=explicit_rule.brand_name,
                message=(
                    "Den eksplicitte brandregel indeholder "
                    "et ugyldigt generation-prefix."
                ),
            )

        return BrandRuleResolution(
            status="VERIFIED_OVERRIDE",
            rule=explicit_rule,
            brand_code=explicit_rule.brand_code,
            brand_name=explicit_rule.brand_name,
            reference_count=(
                explicit_rule.reference_count
            ),
            matching_count=(
                explicit_rule.matching_count
            ),
            confidence=explicit_rule.confidence,
            message=(
                f"Generation-prefix "
                f"{explicit_rule.generation_prefix} "
                "kommer fra en eksplicit "
                "dokumenteret regel."
            ),
        )

    # ---------------------------------------------------------
    # GOLDEN RECORD-KONSENSUS
    # ---------------------------------------------------------

    return resolve_dynamic_brand_rule(
        brand_code=normalized_brand_code,
        products=products,
        minimum_reference_products=(
            minimum_reference_products
        ),
        minimum_confidence=(
            minimum_confidence
        ),
    )


def get_generation_prefix(
    brand_code: str | None,
    products: list[M3Product],
) -> str | None:
    """
    Returnerer kun generation-prefixet,
    når brandreglen er verificeret.
    """

    resolution = resolve_brand_rule(
        brand_code=brand_code,
        products=products,
    )

    if resolution.status not in {
        "VERIFIED_USER_OVERRIDE",
        "VERIFIED_OVERRIDE",
        "VERIFIED_DATA",
    }:
        return None

    if resolution.rule is None:
        return None

    return (
        resolution.rule.generation_prefix
    )


def build_dynamic_brand_rules(
    products: list[M3Product],
) -> dict[str, BrandRuleResolution]:
    """
    Evaluerer samtlige MMBUAR-koder i Golden Record.

    Resultatet indeholder både verificerede brands
    og brands, der kræver brugerens valg.
    """

    brand_codes = sorted(
        {
            clean_value(product.mmbuar)
            for product in products
            if clean_value(product.mmbuar)
        }
    )

    return {
        brand_code: resolve_brand_rule(
            brand_code=brand_code,
            products=products,
        )
        for brand_code in brand_codes
    }