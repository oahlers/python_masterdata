"""Stable presentation helpers for the MASTERDATA review workflow.

This module contains no FastAPI or persistence dependencies.  It converts the
freshly rebuilt MasterDataBuilder preview into the compact result shown after a
review save, while keeping approval blockers separate from optional warnings.
"""

from __future__ import annotations

from typing import Any


def summarize_masterdata_review(
    masterdata: dict[str, Any],
    *,
    changed_fields: list[str],
) -> dict[str, Any]:
    """Build the user-facing result for a saved MASTERDATA review.

    ``masterdata`` must be the serialized result of rebuilding the product with
    the runtime MasterDataBuilder.  Submitted form values are intentionally not
    echoed because Golden Record and template derivation remain authoritative.
    """

    blocking_fields = list(masterdata.get("blocking_fields") or [])
    warning_fields = list(masterdata.get("warning_fields") or [])
    ready_for_verification = not blocking_fields

    return {
        "saved_fields": list(changed_fields),
        "values": {
            "m3_name": masterdata.get("m3_name"),
            "m3_description": masterdata.get("m3_description"),
            "receipt_text": masterdata.get("receipt_text"),
            "item_type": masterdata.get("item_type"),
            "item_group": masterdata.get("item_group"),
            "product_group": masterdata.get("product_group"),
            "product_line": masterdata.get("product_line"),
            "item_category": masterdata.get("item_category"),
        },
        "text_resolution": dict(masterdata.get("text_resolution") or {}),
        "evidence": masterdata.get("evidence") or {
            "item_numbers": list(
                masterdata.get("evidence_item_numbers") or []
            ),
        },
        "blocking_fields": blocking_fields,
        "warning_fields": warning_fields,
        "ready_for_verification": ready_for_verification,
        "next_step": (
            "Vælg produktet og fortsæt til verificering."
            if ready_for_verification
            else "Udfyld de krævede felter før verificering."
        ),
    }
