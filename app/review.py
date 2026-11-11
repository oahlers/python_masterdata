from dataclasses import dataclass, field

from app.models import Evidence, ProductProposal


@dataclass
class ReviewChanges:
    """
    De værdier en bruger vælger eller retter under review.

    None betyder:
    Brugeren har ikke ændret feltet.
    """

    item_type: str | None = None
    item_group: str | None = None
    item_class: str | None = None
    product_line: str | None = None


@dataclass
class ReviewResult:
    proposal: ProductProposal

    changed_fields: list[str] = field(
        default_factory=list
    )

    ready: bool = False


def remove_review_field(
    proposal: ProductProposal,
    field_name: str,
) -> None:
    current = getattr(proposal, "needs_review", ()) or ()

    proposal.needs_review = tuple(
        value
        for value in current
        if value != field_name
    )


def apply_user_value(
    proposal: ProductProposal,
    field_name: str,
    value: str,
) -> None:
    """
    Anvender en brugergodkendt værdi og gemmer evidensen.

    Kun felter der eksplicit understøttes her,
    kan ændres gennem review.
    """

    value = str(value).strip()

    if not value:
        raise ValueError(
            f"{field_name} må ikke være tom."
        )

    field_mapping = {
        "item_type": "item_type",
        "item_group": "item_group",
        "item_class": "item_class",
        "product_line": "product_line",
    }

    model_field = field_mapping.get(
        field_name
    )

    if model_field is None:
        raise ValueError(
            f"Review understøtter ikke feltet "
            f"{field_name!r}."
        )

    setattr(
        proposal,
        model_field,
        value,
    )

    proposal.evidence[field_name] = Evidence(
        field_name=field_name,
        proposed_value=value,
        source="user_review",
        details=(
            "Værdien er valgt eller korrigeret "
            "af brugeren under review."
        ),
    )

    remove_review_field(
        proposal,
        field_name,
    )


def proposal_is_ready(
    proposal: ProductProposal,
) -> bool:
    """
    Et produkt er klar til MMITNO-generering når alle
    obligatoriske klassifikationsfelter er udfyldt.

    item_number må stadig mangle på dette tidspunkt.
    """

    required_values = [
        proposal.brand_code,
        proposal.brand_name,
        proposal.item_type,
        proposal.item_group,
        proposal.item_class,
        proposal.product_line,
    ]

    if not all(required_values):
        return False

    blocking_review = [
        field_name
        for field_name in proposal.needs_review
        if field_name != "item_number"
    ]

    return not blocking_review


def apply_review(
    proposal: ProductProposal,
    changes: ReviewChanges,
) -> ReviewResult:
    """
    Anvender de felter brugeren faktisk har valgt.

    Eksisterende automatiske værdier ændres ikke,
    medmindre brugeren eksplicit sender en ny værdi.
    """

    changed_fields = []

    values = {
        "item_type": changes.item_type,
        "item_group": changes.item_group,
        "item_class": changes.item_class,
        "product_line": changes.product_line,
    }

    for field_name, value in values.items():
        if value is None:
            continue

        apply_user_value(
            proposal=proposal,
            field_name=field_name,
            value=value,
        )

        changed_fields.append(
            field_name
        )

    return ReviewResult(
        proposal=proposal,
        changed_fields=changed_fields,
        ready=proposal_is_ready(
            proposal
        ),
    )