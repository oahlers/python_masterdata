from dataclasses import dataclass, field

from app.golden_record import GoldenRecord
from app.import_analyzer import (
    AnalyzedProduct,
    ImportAnalysis,
)
from app.item_number_reservation import (
    DEFAULT_DATABASE_PATH,
)
from app.item_number_service import (
    assign_item_number,
)


@dataclass
class VerificationItem:
    product_key: str
    product_code: str | None
    ean: str | None
    product_name: str | None

    status: str

    item_number: str | None = None
    incoming_saether_code: str | None = None
    item_number_source: str | None = None

    mmstat: str | None = None
    item_type: str | None = None
    brand_code: str | None = None
    brand_name: str | None = None
    item_group: str | None = None
    item_class: str | None = None
    product_line: str | None = None

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class VerificationBatch:
    analysis_id: str

    requested_count: int
    prepared_count: int
    blocked_count: int

    items: list[VerificationItem] = field(
        default_factory=list
    )

    @property
    def can_continue(self) -> bool:
        return (
            self.prepared_count > 0
            and self.blocked_count == 0
        )


def get_product_key(
    item: AnalyzedProduct,
) -> str:
    source = item.source_product

    if source.ean:
        return source.ean

    if source.product_code:
        return source.product_code

    raise ValueError(
        "Produktet mangler både EAN og product code."
    )


def find_selected_product(
    analysis: ImportAnalysis,
    product_key: str,
) -> AnalyzedProduct | None:
    normalized_key = str(product_key).strip()

    for item in analysis.products:
        source = item.source_product

        if source.ean == normalized_key:
            return item

        if source.product_code == normalized_key:
            return item

    return None


def prepare_single_product(
    item: AnalyzedProduct,
    golden_record: GoldenRecord,
    database_path=DEFAULT_DATABASE_PATH,
) -> VerificationItem:
    source = item.source_product

    try:
        product_key = get_product_key(item)
    except ValueError:
        product_key = (
            source.product_code
            or source.ean
            or "unknown"
        )

    verification = VerificationItem(
        product_key=product_key,
        product_code=source.product_code,
        ean=source.ean,
        product_name=source.product_name,
        status="BLOCKED",
        incoming_saether_code=source.saether_code,
    )

    if item.status != "READY":
        verification.errors.append(
            "Produktet har ikke status READY. "
            f"Aktuel status: {item.status}."
        )
        return verification

    proposal = item.proposal

    if proposal is None:
        verification.errors.append(
            "Produktet mangler ProductProposal."
        )
        return verification

    verification.mmstat = proposal.mmstat
    verification.item_type = proposal.item_type
    verification.brand_code = proposal.brand_code
    verification.brand_name = proposal.brand_name
    verification.item_group = proposal.item_group
    verification.item_class = proposal.item_class
    verification.product_line = proposal.product_line

    blocking_review_fields = [
        field_name
        for field_name in proposal.needs_review
        if field_name != "item_number"
    ]

    if blocking_review_fields:
        verification.errors.append(
            "Produktet mangler stadig review af: "
            + ", ".join(blocking_review_fields)
        )
        return verification

    try:
        item_number = assign_item_number(
            proposal=proposal,
            golden_record=golden_record,
            database_path=database_path,
        )
    except Exception as error:
        verification.errors.append(str(error))
        return verification

    verification.item_number = item_number

    item_number_evidence = proposal.evidence.get(
        "item_number"
    )

    verification.item_number_source = (
        item_number_evidence.source
        if item_number_evidence
        else None
    )

    if source.saether_code:
        verification.warnings.append(
            "Leverandørens indkommende Sæther Code "
            f"{source.saether_code} er valideret og "
            "persistent reserveret til produktet."
        )

    verification.status = "PREPARED"
    return verification


def prepare_verification_batch(
    analysis_id: str,
    analysis: ImportAnalysis,
    product_keys: list[str],
    golden_record: GoldenRecord,
    database_path=DEFAULT_DATABASE_PATH,
) -> VerificationBatch:
    normalized_keys = []
    seen = set()

    for product_key in product_keys:
        normalized_key = str(product_key).strip()

        if not normalized_key:
            continue

        if normalized_key in seen:
            continue

        seen.add(normalized_key)
        normalized_keys.append(normalized_key)

    if not normalized_keys:
        raise ValueError(
            "Vælg mindst ét produkt til verificering."
        )

    items = []

    for product_key in normalized_keys:
        analyzed_product = find_selected_product(
            analysis=analysis,
            product_key=product_key,
        )

        if analyzed_product is None:
            items.append(
                VerificationItem(
                    product_key=product_key,
                    product_code=None,
                    ean=None,
                    product_name=None,
                    status="BLOCKED",
                    errors=[
                        "Produktet blev ikke fundet i analysen."
                    ],
                )
            )
            continue

        items.append(
            prepare_single_product(
                item=analyzed_product,
                golden_record=golden_record,
                database_path=database_path,
            )
        )

    prepared_count = sum(
        item.status == "PREPARED"
        for item in items
    )

    blocked_count = sum(
        item.status == "BLOCKED"
        for item in items
    )

    return VerificationBatch(
        analysis_id=analysis_id,
        requested_count=len(normalized_keys),
        prepared_count=prepared_count,
        blocked_count=blocked_count,
        items=items,
    )
