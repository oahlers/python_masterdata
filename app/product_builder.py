from app.brand_resolver import BrandResolution
from app.family_matcher import FamilyMatchResult
from app.models import (
    Evidence,
    ProductProposal,
    SourceProduct,
)
from app.product_type_rules import (
    find_product_type_rule,
    get_edition,
    get_m3_item_type,
)


def add_review(
    proposal: ProductProposal,
    field_name: str,
) -> None:
    """
    Tilføjer et felt til review-listen uden dubletter.
    """

    if field_name not in proposal.needs_review:
        proposal.needs_review.append(field_name)


def build_new_product_proposal(
    source_product: SourceProduct,
    brand_resolution: BrandResolution | None = None,
    family_match: FamilyMatchResult | None = None,
    item_number: str | None = None,
) -> ProductProposal:
    """
    Bygger et konservativt forslag til en ny M3-vare.

    Kun værdier med dokumenteret evidens udfyldes.
    Alt andet forbliver None og markeres til review.
    """

    proposal = ProductProposal(
        source_product=source_product,
    )

    # ---------------------------------------------------------
    # MMSTAT
    # ---------------------------------------------------------

    proposal.evidence["mmstat"] = Evidence(
        field_name="mmstat",
        proposed_value="10",
        source="business_rule",
        details="Nye produkter oprettes som MMSTAT 10.",
    )

    # ---------------------------------------------------------
    # BMS PRODUCT TYPE / MMITTY
    # ---------------------------------------------------------

    product_type_rule = find_product_type_rule(
        source_product.product_type
    )

    if product_type_rule is None:
        add_review(
            proposal,
            "product_type",
        )

    m3_item_type = get_m3_item_type(
        source_product.product_type
    )

    if m3_item_type is not None:
        proposal.item_type = m3_item_type

        proposal.evidence["item_type"] = Evidence(
            field_name="item_type",
            proposed_value=m3_item_type,
            source="bms_product_type_rule",
            details=(
                f"BMS Product Type "
                f"{source_product.product_type} "
                f"er dokumenteret som "
                f"{product_type_rule.name}."
            ),
        )

    else:
        add_review(
            proposal,
            "item_type",
        )

    # ---------------------------------------------------------
    # EDITION
    # ---------------------------------------------------------

    edition = get_edition(
        source_product.product_type
    )

    if edition is not None:
        proposal.evidence["edition"] = Evidence(
            field_name="edition",
            proposed_value=edition,
            source="bms_product_type_rule",
            details=(
                f"BMS Product Type "
                f"{source_product.product_type} "
                f"giver Edition {edition}."
            ),
        )

    # ---------------------------------------------------------
    # BRAND
    # ---------------------------------------------------------

    if (
        brand_resolution is not None
        and brand_resolution.status == "VERIFIED"
        and brand_resolution.brand_code
        and brand_resolution.brand_name
    ):
        proposal.brand_code = (
            brand_resolution.brand_code
        )

        proposal.brand_name = (
            brand_resolution.brand_name
        )

        proposal.evidence["brand_code"] = Evidence(
            field_name="brand_code",
            proposed_value=proposal.brand_code,
            source="verified_file_brand",
            details=brand_resolution.message,
        )

        proposal.evidence["brand_name"] = Evidence(
            field_name="brand_name",
            proposed_value=proposal.brand_name,
            source="verified_file_brand",
            details=brand_resolution.message,
        )

    else:
        add_review(
            proposal,
            "brand_code",
        )

        add_review(
            proposal,
            "brand_name",
        )

    # ---------------------------------------------------------
    # PRODUKTFAMILIE / KLASSIFIKATION
    # ---------------------------------------------------------

    if (
        family_match is not None
        and family_match.status == "MATCH"
    ):
        proposal.item_group = (
            family_match.item_group
        )

        proposal.item_class = (
            family_match.item_class
        )

        proposal.product_line = (
            family_match.product_line_name
        )

        if family_match.item_group:
            proposal.evidence["item_group"] = Evidence(
                field_name="item_group",
                proposed_value=family_match.item_group,
                source="verified_family_match",
                source_item_numbers=(
                    [family_match.matched_item_number]
                    if family_match.matched_item_number
                    else []
                ),
                details=family_match.message,
            )

        if family_match.item_class:
            proposal.evidence["item_class"] = Evidence(
                field_name="item_class",
                proposed_value=family_match.item_class,
                source="verified_family_match",
                source_item_numbers=(
                    [family_match.matched_item_number]
                    if family_match.matched_item_number
                    else []
                ),
                details=family_match.message,
            )

        if family_match.product_line_code:
            proposal.evidence["product_line"] = Evidence(
                field_name="product_line",
                proposed_value=(
                    family_match.product_line_code
                ),
                source="verified_family_match",
                source_item_numbers=(
                    [family_match.matched_item_number]
                    if family_match.matched_item_number
                    else []
                ),
                details=(
                    f"{family_match.product_line_code} / "
                    f"{family_match.product_line_name}. "
                    f"{family_match.message}"
                ),
            )

    else:
        add_review(
            proposal,
            "item_group",
        )

        add_review(
            proposal,
            "item_class",
        )

        add_review(
            proposal,
            "product_line",
        )
    # ---------------------------------------------------------
    # MMITNO / SÆTHER CODE
    # ---------------------------------------------------------

    if item_number:
        proposal.item_number = item_number

        proposal.evidence["item_number"] = Evidence(
            field_name="item_number",
            proposed_value=item_number,
            source="generated_item_number",
            details=(
                "Nyt MMITNO er genereret efter globalt "
                "collision-check mod Golden Record."
            ),
        )

    else:
        add_review(
            proposal,
            "item_number",
        )

    return proposal