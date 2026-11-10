"""Domain model for the Sæther MASTERDATA export.

This module deliberately contains no SKU creation logic.  It models only the
values that can be written to the existing MASTERDATA template after a product
has been approved.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Iterator


@dataclass(frozen=True, slots=True)
class MasterDataRecord:
    """One product row in the Sæther MASTERDATA workbook.

    ``None`` means that the value is undocumented and must remain blank.  The
    three length columns are intentionally absent: they are formulas owned by
    the Excel template (D, F and H), not product data.
    """

    item_number: str
    m3_name: str

    copy_from_item_number: str | None = None
    m3_description: str | None = None
    receipt_text: str | None = None
    item_type: str | None = None
    item_group: str | None = None
    item_group_description: str | None = None
    product_group: str | None = None
    product_line: str | None = None
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

    def __post_init__(self) -> None:
        if not self.item_number or not self.item_number.strip():
            raise ValueError("item_number is required")
        if not self.m3_name or not self.m3_name.strip():
            raise ValueError("m3_name is required")
        if len(self.m3_name) > 30:
            raise ValueError("m3_name must not exceed 30 characters")
        if self.m3_description is not None and len(self.m3_description) > 60:
            raise ValueError("m3_description must not exceed 60 characters")
        if self.receipt_text is not None and len(self.receipt_text) > 20:
            raise ValueError("receipt_text must not exceed 20 characters")
        if (
            self.item_group_description is not None
            and len(self.item_group_description) > 40
        ):
            raise ValueError(
                "item_group_description must not exceed 40 characters"
            )

    def documented_values(self) -> Iterator[tuple[str, str]]:
        """Yield populated fields, useful for previews and diagnostics."""

        for field in fields(self):
            value = getattr(self, field.name)
            if value is not None:
                yield field.name, value
