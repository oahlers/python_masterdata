"""Domain model for one Sæther MASTERDATA export row.

The frozen SKU engine owns ``item_number``.  A preview may carry ``None`` before
verification reserves MMITNO; approved/export rows may not.  Otherwise ``None``
always means "leave blank" and never "derive by truncating another field".
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Iterator


# This is the deliberately small approval/export gate.  It mirrors the core
# identity and classification columns in the current MASTERDATA template.
# Every other export field may stay blank and can be completed downstream.
MINIMUM_REQUIRED_MASTERDATA_FIELDS = (
    "item_number",
    "m3_name",
    "brand_code",
    "brand_name",
    "item_type",
    "item_group",
    "product_group",
    "product_line",
    "item_category",
    "ref_number",
    "ean",
)


@dataclass(frozen=True, slots=True)
class MasterDataRecord:
    item_number: str | None
    m3_name: str | None = None
    # Brand identity is an approval blocker even though it is not written to a
    # dedicated column in the current MASTERDATA export sheet.  Both halves of
    # the observed MMBUAR/MMBUARTX40 pair are required.
    brand_code: str | None = None
    brand_name: str | None = None

    copy_from_item_number: str | None = None
    m3_description: str | None = None
    receipt_text: str | None = None
    m3_name_status: str | None = None
    m3_name_source: str | None = None
    m3_name_reason: str | None = None
    m3_description_status: str | None = None
    m3_description_source: str | None = None
    m3_description_reason: str | None = None
    receipt_text_status: str | None = None
    receipt_text_source: str | None = None
    receipt_text_reason: str | None = None
    receipt_text_required: bool = False
    item_type: str | None = None
    item_group: str | None = None
    # Exported to K only for a genuinely new item group.
    item_group_description: str | None = None
    product_group: str | None = None
    product_line: str | None = None
    # Combined code + description from the template reference sheet.
    item_category: str | None = None
    ref_number: str | None = None
    ean: str | None = None
    edition: str | None = "NY"
    net_content: str | None = None
    content_unit: str | None = None
    delivery_week: str | None = None
    supplier_number_for_pos: str | None = None
    gender: str | None = None
    distribution_channel: str | None = None
    cogs: str | None = None
    rrp_dkk: str | None = None
    rrp_sek: str | None = None
    rrp_nok: str | None = None
    rrp_eur: str | None = None

    # Internal evidence retained for review/UI; not mapped to Excel cells.
    item_group_evidence_description: str | None = None
    product_group_description: str | None = None
    product_line_description: str | None = None
    item_category_code: str | None = None
    item_category_description: str | None = None
    evidence_item_numbers: tuple[str, ...] = ()
    review_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _check_length("m3_name", self.m3_name, 30)
        _check_length("m3_description", self.m3_description, 60)
        _check_length("receipt_text", self.receipt_text, 20)
        if self.item_type == "12" and not _is_blank(self.receipt_text):
            raise ValueError("receipt_text is not applicable for item type 12")
        _check_length(
            "item_group_description",
            self.item_group_description,
            40,
        )

    def documented_values(self) -> Iterator[tuple[str, str]]:
        """Yield populated scalar export fields for diagnostics/previews."""

        internal = {
            "brand_code",
            "brand_name",
            "item_group_evidence_description",
            "product_group_description",
            "product_line_description",
            "item_category_code",
            "item_category_description",
            "evidence_item_numbers",
            "review_fields",
            "m3_name_status",
            "m3_name_source",
            "m3_name_reason",
            "m3_description_status",
            "m3_description_source",
            "m3_description_reason",
            "receipt_text_status",
            "receipt_text_source",
            "receipt_text_reason",
            "receipt_text_required",
        }
        for field in fields(self):
            if field.name in internal:
                continue
            value = getattr(self, field.name)
            if value is not None:
                yield field.name, value

    @property
    def missing_required_fields(self) -> tuple[str, ...]:
        """Return only fields that must exist before approval/export.

        Optional template columns and non-blocking review items are excluded.
        This keeps incomplete supplier attributes visible without turning them
        into a reason to reject an otherwise creatable product.
        """

        return tuple(
            field_name
            for field_name in self.required_masterdata_fields
            if _is_blank(getattr(self, field_name))
        )

    @property
    def required_masterdata_fields(self) -> tuple[str, ...]:
        """Return the approval gate including documented item-type rules."""

        if self.item_type == "00":
            return (*MINIMUM_REQUIRED_MASTERDATA_FIELDS, "receipt_text")
        return MINIMUM_REQUIRED_MASTERDATA_FIELDS

    @property
    def warning_fields(self) -> tuple[str, ...]:
        """Return review items that do not block SKU approval or export."""

        required = set(self.required_masterdata_fields)
        return tuple(
            field_name
            for field_name in self.review_fields
            if field_name not in required
        )

    @property
    def missing_preverification_fields(self) -> tuple[str, ...]:
        """Return blockers a reviewer can resolve before SKU verification.

        ``item_number`` is deliberately excluded: the reservation step owns it,
        so its expected absence on the analysis page is not a review defect.
        """

        return tuple(
            field_name
            for field_name in self.missing_required_fields
            if field_name != "item_number"
        )

    @property
    def ready_for_verification(self) -> bool:
        return not self.missing_preverification_fields

    @property
    def ready_for_approval(self) -> bool:
        return not self.missing_required_fields


def _check_length(field_name: str, value: str | None, limit: int) -> None:
    if value is not None and len(value) > limit:
        raise ValueError(f"{field_name} must not exceed {limit} characters")


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
