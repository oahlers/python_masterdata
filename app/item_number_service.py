from app.brand_rules import resolve_brand_rule
from app.golden_record import GoldenRecord
from app.item_number_generator import (
    generate_item_number_for_brand,
)
from app.item_number_reservation import (
    DEFAULT_DATABASE_PATH,
    get_reservation_for_product,
    item_number_is_reserved,
    reserve_item_number,
)
from app.models import Evidence, ProductProposal
from app.product_resolver import ProductResolver
from app.review import proposal_is_ready


def _remove_item_number_review(
    proposal: ProductProposal,
) -> None:
    while "item_number" in proposal.needs_review:
        proposal.needs_review.remove("item_number")


def _set_item_number(
    proposal: ProductProposal,
    item_number: str,
    evidence_source: str,
    evidence_details: str,
) -> str:
    proposal.item_number = item_number
    proposal.evidence["item_number"] = Evidence(
        field_name="item_number",
        proposed_value=item_number,
        source=evidence_source,
        details=evidence_details,
    )
    _remove_item_number_review(proposal)
    return item_number


def _validate_new_product(
    proposal: ProductProposal,
    golden_record: GoldenRecord,
) -> None:
    if proposal is None:
        raise ValueError(
            "MMITNO kan kun tildeles et nyt ProductProposal. "
            "Eksisterende M3-produkter må ikke få et nyt MMITNO."
        )

    resolution = ProductResolver(
        golden_record
    ).resolve(proposal.source_product)

    if resolution.status != "NEW_PRODUCT":
        raise ValueError(
            "Produktet må ikke få MMITNO. "
            f"{resolution.message}"
        )


def _validate_proposal_ready(
    proposal: ProductProposal,
) -> None:
    if not proposal_is_ready(proposal):
        raise ValueError(
            "Produktet er ikke klar til "
            "MMITNO-tildeling."
        )

    if not proposal.brand_code:
        raise ValueError(
            "Produktet mangler brandkode."
        )


def assign_incoming_item_number(
    proposal: ProductProposal,
    golden_record: GoldenRecord,
    database_path=DEFAULT_DATABASE_PATH,
) -> str:
    """
    Validerer og reserverer en Sæther Code fra leverandørfilen.

    Incoming-numre genereres aldrig om. Ved konflikt blokeres
    produktet, så nummeret kan afklares manuelt.
    """
    _validate_new_product(
        proposal=proposal,
        golden_record=golden_record,
    )
    _validate_proposal_ready(proposal)

    source_product = proposal.source_product
    incoming = str(
        source_product.saether_code or ""
    ).strip()

    if not incoming:
        raise ValueError(
            "Produktet indeholder ingen indkommende Sæther Code."
        )

    if not incoming.isdigit():
        raise ValueError(
            "Indkommende Sæther Code skal kun bestå af cifre."
        )

    resolution = resolve_brand_rule(
        brand_code=proposal.brand_code,
        products=golden_record.products,
    )

    if resolution.rule is None:
        observed = [
            prefix
            for prefix, _ in resolution.prefix_counts
        ]
        raise ValueError(
            f"Brand {proposal.brand_code} har ikke et sikkert "
            f"generation-prefix. Status: {resolution.status}. "
            f"Observerede prefixes: {observed}"
        )

    expected_prefix = str(
        resolution.rule.generation_prefix
    ).strip()

    if not incoming.startswith(expected_prefix):
        raise ValueError(
            f"Indkommende Sæther Code {incoming} matcher ikke "
            f"brandets verificerede generation-prefix "
            f"{expected_prefix}."
        )

    golden_record_product = (
        golden_record.find_by_item_number(incoming)
    )

    if golden_record_product is not None:
        raise ValueError(
            f"Indkommende Sæther Code {incoming} findes allerede "
            "som MMITNO i Golden Record."
        )

    existing_reservation = get_reservation_for_product(
        product=source_product,
        database_path=database_path,
    )

    if existing_reservation is not None:
        if existing_reservation.item_number != incoming:
            raise ValueError(
                "Produktet har allerede persistent reserveret "
                f"MMITNO {existing_reservation.item_number}, men "
                f"leverandørfilen angiver {incoming}."
            )

        return _set_item_number(
            proposal=proposal,
            item_number=existing_reservation.item_number,
            evidence_source="incoming_saether_code_existing_reservation",
            evidence_details=(
                "Indkommende Sæther Code matcher produktets "
                "eksisterende persistente reservation."
            ),
        )

    if item_number_is_reserved(
        incoming,
        database_path=database_path,
    ):
        raise ValueError(
            f"Indkommende Sæther Code {incoming} er allerede "
            "reserveret til et andet produkt."
        )

    reservation = reserve_item_number(
        product=source_product,
        item_number=incoming,
        database_path=database_path,
    )

    return _set_item_number(
        proposal=proposal,
        item_number=reservation.item_number,
        evidence_source="incoming_saether_code",
        evidence_details=(
            "Sæther Code kom fra leverandørfilen, blev "
            "format-, prefix- og collision-valideret og "
            "derefter persistent reserveret."
        ),
    )


def assign_generated_item_number(
    proposal: ProductProposal,
    golden_record: GoldenRecord,
    database_path=DEFAULT_DATABASE_PATH,
) -> str:
    """
    Finder eller genererer et stabilt MMITNO, når leverandøren
    ikke allerede har angivet en Sæther Code.
    """
    _validate_new_product(
        proposal=proposal,
        golden_record=golden_record,
    )

    source_product = proposal.source_product

    existing_reservation = get_reservation_for_product(
        product=source_product,
        database_path=database_path,
    )

    if existing_reservation is not None:
        return _set_item_number(
            proposal=proposal,
            item_number=existing_reservation.item_number,
            evidence_source="existing_reservation",
            evidence_details=(
                "Eksisterende MMITNO-reservation er genbrugt."
            ),
        )

    _validate_proposal_ready(proposal)

    reserved_numbers = set()

    for _ in range(100):
        candidate = generate_item_number_for_brand(
            brand_code=proposal.brand_code,
            golden_record=golden_record,
            reserved_numbers=reserved_numbers,
        )

        if item_number_is_reserved(
            candidate,
            database_path=database_path,
        ):
            reserved_numbers.add(candidate)
            continue

        reservation = reserve_item_number(
            product=source_product,
            item_number=candidate,
            database_path=database_path,
        )

        return _set_item_number(
            proposal=proposal,
            item_number=reservation.item_number,
            evidence_source="persistent_reservation",
            evidence_details=(
                "Nyt MMITNO er genereret, collision-checket "
                "og persistent reserveret."
            ),
        )

    raise RuntimeError(
        "Kunne ikke finde et ledigt MMITNO "
        "efter 100 forsøg."
    )


def assign_item_number(
    proposal: ProductProposal,
    golden_record: GoldenRecord,
    database_path=DEFAULT_DATABASE_PATH,
) -> str:
    """
    Autoritativ indgang til MMITNO-tildeling.

    - Incoming Sæther Code: valideres og reserveres.
    - Ingen incoming kode: eksisterende generation anvendes.
    """
    if proposal is None:
        raise ValueError(
            "MMITNO kan kun tildeles et nyt ProductProposal."
        )

    if proposal.source_product.saether_code:
        return assign_incoming_item_number(
            proposal=proposal,
            golden_record=golden_record,
            database_path=database_path,
        )

    return assign_generated_item_number(
        proposal=proposal,
        golden_record=golden_record,
        database_path=database_path,
    )
