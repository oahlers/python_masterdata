from dataclasses import dataclass

from app.brand_rule_store import save_override
from app.brand_rules import (
    BrandRuleResolution,
    resolve_brand_rule,
)
from app.models import M3Product


@dataclass(frozen=True)
class BrandPrefixOption:
    prefix: str
    count: int
    percentage: float


@dataclass(frozen=True)
class BrandReview:
    brand_code: str
    brand_name: str | None

    status: str
    requires_review: bool

    options: tuple[BrandPrefixOption, ...] = ()

    message: str = ""


def get_brand_review(
    brand_code: str,
    products: list[M3Product],
) -> BrandReview:
    """
    Bygger den information UI'et senere skal vise.

    Tvetydige brands viser alle observerede,
    gyldige trecifrede prefixes som valgmuligheder.
    """

    resolution: BrandRuleResolution = resolve_brand_rule(
        brand_code=brand_code,
        products=products,
    )

    if resolution.rule is not None:
        return BrandReview(
            brand_code=brand_code,
            brand_name=resolution.brand_name,
            status=resolution.status,
            requires_review=False,
            message=resolution.message,
        )

    total = sum(
        count
        for _, count in resolution.prefix_counts
    )

    options = []

    for prefix, count in resolution.prefix_counts:
        if len(prefix) != 3 or not prefix.isdigit():
            continue

        percentage = (
            count / total
            if total
            else 0.0
        )

        options.append(
            BrandPrefixOption(
                prefix=prefix,
                count=count,
                percentage=percentage,
            )
        )

    return BrandReview(
        brand_code=brand_code,
        brand_name=resolution.brand_name,
        status=resolution.status,
        requires_review=True,
        options=tuple(options),
        message=resolution.message,
    )


def approve_brand_prefix(
    review: BrandReview,
    generation_prefix: str,
) -> dict:
    """
    Gemmer brugerens valg som fremtidig brandregel.

    Brugeren kan kun vælge blandt de prefixes,
    som reviewet faktisk viste.
    """

    if not review.requires_review:
        raise ValueError(
            "Brandet kræver ikke manuel prefix-review."
        )

    allowed_prefixes = {
        option.prefix
        for option in review.options
    }

    if generation_prefix not in allowed_prefixes:
        raise ValueError(
            f"Prefix {generation_prefix} er ikke en "
            f"godkendt valgmulighed. "
            f"Muligheder: {sorted(allowed_prefixes)}"
        )

    if not review.brand_name:
        raise ValueError(
            "Brandnavnet mangler og valget kan ikke gemmes."
        )

    return save_override(
        brand_code=review.brand_code,
        brand_name=review.brand_name,
        generation_prefix=generation_prefix,
        observed_prefixes=allowed_prefixes,
    )