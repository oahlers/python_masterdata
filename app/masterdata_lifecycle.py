"""Small, explicit MVP lifecycle for item creation.

The lifecycle deliberately separates identity/Saether Code reservation from
MASTERDATA completion.  It is pure and side-effect free so API and UI code use
one source of truth for stages, blockers and next actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


ANALYSIS = "ANALYSIS"
IDENTITY_REVIEW = "IDENTITY_REVIEW"
CODE_READY = "CODE_READY"
CODE_RESERVED = "CODE_RESERVED"
MASTERDATA_REVIEW = "MASTERDATA_REVIEW"
READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
APPROVED = "APPROVED"
EXISTING = "EXISTING"
IDENTITY_CONFLICT = "IDENTITY_CONFLICT"


@dataclass(frozen=True, slots=True)
class LifecycleState:
    stage: str
    label: str
    next_action: str
    blockers: tuple[str, ...] = ()
    can_reserve_code: bool = False
    can_approve: bool = False
    can_download: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "label": self.label,
            "next_action": self.next_action,
            "blockers": list(self.blockers),
            "can_reserve_code": self.can_reserve_code,
            "can_approve": self.can_approve,
            "can_download": self.can_download,
        }


def identity_blockers(item: Any) -> tuple[str, ...]:
    """Return only blockers needed before a Sæther Code may be reserved."""

    source = _read(item, "source_product", "source")
    proposal = _read(item, "proposal", "product_proposal")
    blockers: list[str] = []
    if not _text(_read(source, "ean", "gtin")) and not _text(
        _read(source, "product_code", "supplier_item_number", "ref_number")
    ):
        blockers.append("product_identity")
    if not _text(_read(source, "product_name", "name")):
        blockers.append("product_name")
    if not _text(_read(proposal, "brand_code", "mmbuar")):
        blockers.append("brand_code")
    if not _text(_read(proposal, "brand_name", "mmbuartx40")):
        blockers.append("brand_name")
    return tuple(dict.fromkeys(blockers))


def lifecycle_state(
    item: Any,
    masterdata_preview: Mapping[str, Any] | None = None,
    *,
    approved: bool = False,
) -> LifecycleState:
    """Compute the current stage without mutating importer/domain objects."""

    status = str(_read(item, "status") or "").strip().upper()
    proposal = _read(item, "proposal", "product_proposal")
    item_number = _text(_read(proposal, "item_number", "mmitno"))

    if status == "EXISTING":
        return LifecycleState(EXISTING, "Eksisterende", "Ingen handling nødvendig.")
    if status == "AMBIGUOUS" or bool(_read(item, "identifier_conflict")):
        return LifecycleState(
            IDENTITY_CONFLICT,
            "Identitetskonflikt",
            "Afklar EAN/leverandørreference før produktet kan fortsætte.",
            ("identifier_conflict",),
        )
    if approved:
        return LifecycleState(
            APPROVED,
            "Godkendt",
            "Download MASTERDATA.xlsx.",
            can_download=True,
        )

    identity = identity_blockers(item)
    if identity:
        return LifecycleState(
            IDENTITY_REVIEW,
            "Kodeklar – identitet mangler",
            "Bekræft produktidentitet og vælg dokumenteret brand.",
            identity,
        )
    if not item_number:
        return LifecycleState(
            CODE_READY,
            "Klar til Sæther Code",
            "Reservér Sæther Code. MASTERDATA udfyldes bagefter.",
            can_reserve_code=True,
        )

    preview = masterdata_preview or {}
    blockers = tuple(
        field
        for field in (preview.get("blocking_fields") or ())
        if field != "item_number"
    )
    if blockers or preview.get("error"):
        if preview.get("error") and "masterdata" not in blockers:
            blockers = (*blockers, "masterdata")
        return LifecycleState(
            MASTERDATA_REVIEW,
            "Sæther Code reserveret – færdiggør MASTERDATA",
            "Gennemgå kun de resterende påkrævede felter.",
            tuple(dict.fromkeys(blockers)),
        )

    return LifecycleState(
        READY_FOR_APPROVAL,
        "Klar til godkendelse",
        "Verificér de afledte værdier og godkend produktet.",
        can_approve=True,
    )


def _read(obj: Any, *names: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        folded = {str(key).casefold(): value for key, value in obj.items()}
        for name in names:
            value = folded.get(name.casefold())
            if value is not None:
                return value
        return None
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None
