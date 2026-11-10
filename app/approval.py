from dataclasses import dataclass
from datetime import datetime, timezone

from app.golden_record import GoldenRecord
from app.item_number_reservation import (
    DEFAULT_DATABASE_PATH,
    get_reservation_for_product,
)
from app.models import ProductProposal
from app.product_resolver import ProductResolver


@dataclass(frozen=True)
class ApprovedProduct:
    """
    Et produkt som har passeret den manuelle approval-gate.

    Kun ApprovedProduct må senere accepteres af M3-writeren.
    """

    proposal: ProductProposal

    approved: bool
    approved_at: str

    approval_source: str = "user"


def validate_proposal_for_approval(
    proposal: ProductProposal,
    golden_record: GoldenRecord,
    database_path=DEFAULT_DATABASE_PATH,
) -> list[str]:
    """
    Returnerer alle blokeringer, der forhindrer godkendelse.

    Tom liste betyder, at produktet teknisk kan godkendes.
    """

    errors = []

    source_product = proposal.source_product

    # ---------------------------------------------------------
    # PRODUKTET MÅ IKKE ALLEREDE EKSISTERE
    # ---------------------------------------------------------

    resolution = ProductResolver(
        golden_record
    ).resolve(source_product)

    if resolution.status != "NEW_PRODUCT":
        errors.append(
            "Produktet findes allerede i Golden Record."
        )

    # ---------------------------------------------------------
    # OBLIGATORISKE FELTER
    # ---------------------------------------------------------

    required_fields = {
        "item_number": proposal.item_number,
        "mmstat": proposal.mmstat,
        "item_type": proposal.item_type,
        "brand_code": proposal.brand_code,
        "brand_name": proposal.brand_name,
        "item_group": proposal.item_group,
        "item_class": proposal.item_class,
        "product_line": proposal.product_line,
    }

    for field_name, value in required_fields.items():
        if value is None or not str(value).strip():
            errors.append(
                f"Feltet {field_name} mangler."
            )

    # ---------------------------------------------------------
    # REVIEW SKAL VÆRE AFSLUTTET
    # ---------------------------------------------------------

    if proposal.needs_review:
        errors.append(
            "Produktet har stadig felter, der kræver review: "
            + ", ".join(proposal.needs_review)
        )

    # ---------------------------------------------------------
    # MMSTAT
    # ---------------------------------------------------------

    if proposal.mmstat != "10":
        errors.append(
            "Nye produkter skal have MMSTAT 10."
        )

    # ---------------------------------------------------------
    # MMITNO SKAL VÆRE PERSISTENT RESERVERET
    # ---------------------------------------------------------

    reservation = get_reservation_for_product(
        product=source_product,
        database_path=database_path,
    )

    if reservation is None:
        errors.append(
            "Produktets MMITNO er ikke persistent reserveret."
        )

    elif proposal.item_number != reservation.item_number:
        errors.append(
            "Produktets MMITNO matcher ikke den "
            "persistente reservation."
        )

    # ---------------------------------------------------------
    # GLOBAL GOLDEN RECORD COLLISION
    # ---------------------------------------------------------

    if (
        proposal.item_number
        and golden_record.find_by_item_number(
            proposal.item_number
        )
        is not None
    ):
        errors.append(
            "Produktets MMITNO findes allerede "
            "i Golden Record."
        )

    return errors


def approve_product(
    proposal: ProductProposal,
    golden_record: GoldenRecord,
    database_path=DEFAULT_DATABASE_PATH,
    confirmed: bool = False,
) -> ApprovedProduct:
    """
    Godkender produktet eksplicit.

    confirmed skal være True.
    Approval sker dermed aldrig automatisk.
    """

    if confirmed is not True:
        raise ValueError(
            "Produktet kræver eksplicit "
            "brugergodkendelse."
        )

    errors = validate_proposal_for_approval(
        proposal=proposal,
        golden_record=golden_record,
        database_path=database_path,
    )

    if errors:
        raise ValueError(
            "Produktet kan ikke godkendes:\n- "
            + "\n- ".join(errors)
        )

    approved_at = (
        datetime.now(timezone.utc).isoformat()
    )

    return ApprovedProduct(
        proposal=proposal,
        approved=True,
        approved_at=approved_at,
        approval_source="user",
    )