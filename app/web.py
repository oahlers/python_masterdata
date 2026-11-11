import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path



from fastapi import (
    FastAPI,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask



from app.approval import (
    ApprovedProduct,
    approve_product,
)
from app.classification_feedback_store import (
    save_feedback,
)
from app.golden_record import GoldenRecord
from app.import_analyzer import (
    AnalyzedProduct,
    ImportAnalysis,
    analyze_import,
)
from app.masterdata_builder import MasterDataBuilder
from app.masterdata_excel import MasterDataExcelExporter
from app.masterdata_reference import TemplateReferenceData
from app.masterdata_registry import GoldenRecordOptionRegistry
from app.masterdata_lifecycle import (
    CODE_READY,
    READY_FOR_APPROVAL,
    lifecycle_state,
)
from app.masterdata_ui import summarize_masterdata_review
from app.review import (
    ReviewChanges,
    apply_review,
)
from app.review_suggestions import (
    get_review_suggestions,
)
from app.verification import (
    VerificationBatch,
    VerificationItem,
    prepare_verification_batch,
)




MASTERDATA_TEMPLATE_PATH = Path(
    "templates/saether_masterdata_template.xlsx"
)
MASTERDATA_REFERENCE_TEMPLATE_PATH = Path(
    "templates/saether_masterdata_template_reference.xlsx"
)
MASTERDATA_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "spreadsheetml.sheet"
)

AUTOMATIC_MASTERDATA_FIELDS = frozenset(
    {
        "m3_name",
        "item_type",
        "item_group",
        "product_group",
        "product_line",
        "item_category",
    }
)




golden_record: GoldenRecord | None = None
classification_registry: GoldenRecordOptionRegistry | None = None
_classification_registry_source: object | None = None


def startup() -> None:
    global golden_record, classification_registry, _classification_registry_source

    print("Indlæser Golden Record...")
    golden_record = GoldenRecord().load()
    classification_registry = GoldenRecordOptionRegistry(golden_record)
    _classification_registry_source = golden_record
    print(f"Golden Record klar: {len(golden_record):,} produkter")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    startup()
    yield


app = FastAPI(
    title="Sæther Masterdata Automation",
    version="0.8.0",
    lifespan=lifespan,
)




# ---------------------------------------------------------
# APPROVAL RESULT MODELS
# ---------------------------------------------------------




@dataclass
class ApprovalItem:
    product_key: str
    product_code: str | None
    ean: str | None
    product_name: str | None
    item_number: str | None
    status: str
    approved_at: str | None = None
    approval_source: str | None = None
    errors: list[str] = field(default_factory=list)




@dataclass
class ApprovalBatch:
    analysis_id: str
    requested_count: int
    approved_count: int
    blocked_count: int
    items: list[ApprovalItem] = field(default_factory=list)
    approved_products: list[ApprovedProduct] = field(default_factory=list)



    @property
    def ready_for_m3(self) -> bool:
        return (
            self.requested_count > 0
            and self.approved_count == self.requested_count
            and self.blocked_count == 0
        )




# ---------------------------------------------------------
# MIDLERTIDIGE SESSIONLAGRE
# ---------------------------------------------------------




analysis_sessions: dict[str, ImportAnalysis] = {}
verification_batches: dict[str, VerificationBatch] = {}
approved_batches: dict[str, ApprovalBatch] = {}
code_reservation_batches: dict[str, dict[str, dict]] = {}




# ---------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------




class ReviewRequest(BaseModel):
    brand_code: str | None = None
    brand_name: str | None = None
    item_type: str | None = None
    item_group: str | None = None
    item_class: str | None = None
    product_line: str | None = None
    item_category: str | None = None
    m3_name: str | None = None
    m3_description: str | None = None
    receipt_text: str | None = None
    item_group_description: str | None = None
    is_new_item_group: bool | None = None
    masterdata_review: bool = False
    override_fields: list[str] = Field(default_factory=list)
    reset_override_fields: list[str] = Field(default_factory=list)
    override_reason: str | None = None




class PrepareRequest(BaseModel):
    product_keys: list[str]


class ReserveCodeRequest(BaseModel):
    product_keys: list[str]




class ApproveRequest(BaseModel):
    confirmed: bool = False




# ---------------------------------------------------------
# STARTUP / HEALTH
# ---------------------------------------------------------




@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "golden_record_loaded": golden_record is not None,
        "golden_record_products": (
            len(golden_record)
            if golden_record
            else 0
        ),
        "active_analysis_sessions": len(analysis_sessions),
        "active_verification_batches": len(verification_batches),
        "active_approved_batches": len(approved_batches),
        "active_code_reservation_batches": len(code_reservation_batches),
    }


def get_masterdata_builder(
    *,
    template_reference: TemplateReferenceData | None = None,
) -> MasterDataBuilder:
    """Create the one runtime builder used by preview, approval and export."""

    if golden_record is None:
        raise ValueError("Golden Record er ikke indlæst.")
    return MasterDataBuilder(
        golden_record=golden_record,
        template_reference=(
            template_reference
            if template_reference is not None
            else get_masterdata_reference()
        ),
    )


def get_masterdata_reference() -> TemplateReferenceData:
    # Classification and UI options come from the untouched reference
    # workbook.  The clean production template is exclusively an export
    # target.  Falling back keeps isolated tests and older installations
    # functional until both current files have been copied into /templates.
    configured_reference = MASTERDATA_REFERENCE_TEMPLATE_PATH
    path = (
        configured_reference
        if configured_reference.is_file()
        else MASTERDATA_TEMPLATE_PATH
    ).resolve()
    return _cached_masterdata_reference(
        str(path),
        path.stat().st_mtime_ns,
    )


def get_classification_registry() -> GoldenRecordOptionRegistry:
    """Return an index for the currently installed Golden Record.

    Tests and reload-mode development replace ``golden_record`` directly, so
    identity is checked before reusing the index.
    """

    global classification_registry, _classification_registry_source
    if golden_record is None:
        raise ValueError("Golden Record er ikke indlæst.")
    if (
        classification_registry is None
        or _classification_registry_source is not golden_record
    ):
        classification_registry = GoldenRecordOptionRegistry(golden_record)
        _classification_registry_source = golden_record
    return classification_registry


@lru_cache(maxsize=4)
def _cached_masterdata_reference(
    path: str,
    _modified_at_ns: int,
) -> TemplateReferenceData:
    return TemplateReferenceData.from_xlsx(path)


def _masterdata_review_values(item: AnalyzedProduct) -> dict:
    merged: dict = {}
    proposal = getattr(item, "proposal", None)
    source = getattr(item, "source_product", None)
    for obj in (proposal, source, item):
        if obj is None:
            continue
        direct = getattr(obj, "masterdata_review", None)
        if isinstance(direct, dict):
            merged.update(direct)
        raw_data = getattr(obj, "raw_data", None)
        if isinstance(raw_data, dict):
            nested = raw_data.get("masterdata_review")
            if isinstance(nested, dict):
                merged.update(nested)
    return merged


def _save_masterdata_review_values(
    item: AnalyzedProduct,
    values: dict,
) -> None:
    proposal = getattr(item, "proposal", None)
    if proposal is None:
        raise ValueError("Produktet mangler et ProductProposal.")
    try:
        setattr(proposal, "masterdata_review", values)
        return
    except AttributeError:
        pass

    raw_data = getattr(proposal, "raw_data", None)
    if not isinstance(raw_data, dict):
        raw_data = getattr(item.source_product, "raw_data", None)
    if not isinstance(raw_data, dict):
        raise ValueError("ProductProposal kan ikke gemme MASTERDATA-review.")
    raw_data["masterdata_review"] = values




# ---------------------------------------------------------
# ANALYSIS SERIALIZATION
# ---------------------------------------------------------




def serialize_suggestion(suggestion) -> dict:
    return {
        "field_name": suggestion.field_name,
        "suggested_value": suggestion.suggested_value,
        "evidence_count": suggestion.evidence_count,
        "source": suggestion.source,
        "message": suggestion.message,
    }




def _text_resolution_state(
    status: str | None,
    source: str | None,
) -> str:
    if status == "not_applicable":
        return "not_applicable"
    if status == "awaiting_item_type":
        return "awaiting_item_type"
    if status == "documented":
        return "review" if source == "reviewed_value" else "automatic"
    if status == "missing_documented_source":
        return "unavailable"
    return "review"


def _classification_options(item: AnalyzedProduct) -> dict:
    proposal = getattr(item, "proposal", None)
    source = getattr(item, "source_product", None)
    brand_code = getattr(proposal, "brand_code", None) or getattr(
        source, "brand_code", None
    )
    brand_name = getattr(proposal, "brand_name", None) or getattr(
        source, "brand_name", None
    )
    return get_classification_registry().classification_options(
        brand_code=brand_code,
        brand_name=brand_name,
        source_product=source,
        proposal=proposal,
        selected_item_group=getattr(proposal, "item_group", None),
    )


def serialize_masterdata_preview(item: AnalyzedProduct) -> dict:
    try:
        documented_options = _classification_options(item)
    except ValueError:
        documented_options = {
            "selected_brand": None,
            "item_group_options": [],
            "item_class_options": [],
            "item_type_options": [],
            "family_candidates": [],
            "family_candidate_count": 0,
            "has_more_family_candidates": False,
            "auto_family": None,
            "ambiguous": False,
        }
    try:
        reference = get_masterdata_reference()
        item_category_option_details = reference.item_category_option_payload()
        product_line_option_details = reference.product_line_option_payload()
        # Keep the original string-array API contract for existing clients;
        # the parallel detail payload gives the React UI descriptive labels.
        item_category_options = [
            option["value"] for option in item_category_option_details
        ]
        product_line_options = [
            option["value"] for option in product_line_option_details
        ]
    except (FileNotFoundError, ValueError) as error:
        return {
            "review_fields": ["masterdata"],
            "blocking_fields": ["masterdata"],
            "approval_blocking_fields": ["masterdata"],
            "warning_fields": [],
            "pending_generated_fields": [],
            "ready_for_verification": False,
            "ready_for_approval": False,
            "item_category_options": [],
            "product_line_options": [],
            "item_category_option_details": [],
            "product_line_option_details": [],
            **documented_options,
            "error": str(error),
        }

    try:
        record = get_masterdata_builder(
            template_reference=reference,
        ).build_preview(item)
    except (FileNotFoundError, ValueError) as error:
        # Reference options remain usable even if this individual product cannot
        # be classified.  A row-level error must not collapse both selectors.
        return {
            "review_fields": ["masterdata"],
            "blocking_fields": ["masterdata"],
            "approval_blocking_fields": ["masterdata"],
            "warning_fields": [],
            "pending_generated_fields": [],
            "ready_for_verification": False,
            "ready_for_approval": False,
            "item_category_options": item_category_options,
            "product_line_options": product_line_options,
            "item_category_option_details": item_category_option_details,
            "product_line_option_details": product_line_option_details,
            **documented_options,
            "error": str(error),
        }

    stored_review = _masterdata_review_values(item)
    automatic_values = dict(stored_review.get("__automatic_values") or {})
    override_reasons = dict(stored_review.get("__override_reasons") or {})
    override_fields = sorted(
        field_name
        for field_name in AUTOMATIC_MASTERDATA_FIELDS
        if field_name in stored_review
        and stored_review.get(field_name) is not None
        and str(stored_review.get(field_name)).strip()
    )
    current_values = {
        "m3_name": record.m3_name,
        "item_type": record.item_type,
        "item_group": record.item_group,
        "product_group": record.product_group,
        "product_line": record.product_line,
        "item_category": record.item_category,
    }
    for field_name, value in current_values.items():
        if field_name not in override_fields:
            automatic_values[field_name] = value

    return {
        "item_number": record.item_number,
        "m3_name": record.m3_name,
        "brand_code": record.brand_code,
        "brand_name": record.brand_name,
        "m3_description": record.m3_description,
        "receipt_text": record.receipt_text,
        "text_resolution": {
            "m3_name": {
                "value": record.m3_name,
                "status": record.m3_name_status,
                "source": record.m3_name_source,
                "reason": record.m3_name_reason,
                "required": True,
                "state": _text_resolution_state(
                    record.m3_name_status,
                    record.m3_name_source,
                ),
            },
            "m3_description": {
                "value": record.m3_description,
                "status": record.m3_description_status,
                "source": record.m3_description_source,
                "reason": record.m3_description_reason,
                "required": False,
                "state": _text_resolution_state(
                    record.m3_description_status,
                    record.m3_description_source,
                ),
            },
            "receipt_text": {
                "value": record.receipt_text,
                "status": record.receipt_text_status,
                "source": record.receipt_text_source,
                "reason": record.receipt_text_reason,
                "required": record.receipt_text_required,
                "state": _text_resolution_state(
                    record.receipt_text_status,
                    record.receipt_text_source,
                ),
            },
        },
        "item_type": record.item_type,
        "item_group": record.item_group,
        "item_group_description": record.item_group_description,
        "item_group_evidence_description": (
            record.item_group_evidence_description
        ),
        "product_group": record.product_group,
        "product_group_description": record.product_group_description,
        "product_line": record.product_line,
        "product_line_description": record.product_line_description,
        "item_category": record.item_category,
        "item_category_code": record.item_category_code,
        "item_category_description": record.item_category_description,
        "evidence_item_numbers": list(record.evidence_item_numbers),
        "evidence": {
            "item_numbers": list(record.evidence_item_numbers),
            "item_group_description": (
                record.item_group_evidence_description
            ),
            "product_group_description": (
                record.product_group_description
            ),
            "product_line_description": (
                record.product_line_description
            ),
            "item_category_code": record.item_category_code,
            "item_category_description": (
                record.item_category_description
            ),
        },
        "review_fields": list(record.review_fields),
        # Analysis-page blockers are fields a reviewer can resolve.  MMITNO is
        # generated later by verification and is therefore reported separately.
        "blocking_fields": list(record.missing_preverification_fields),
        "approval_blocking_fields": list(record.missing_required_fields),
        "warning_fields": list(record.warning_fields),
        "pending_generated_fields": (
            ["item_number"] if record.item_number is None else []
        ),
        "ready_for_verification": record.ready_for_verification,
        "ready_for_approval": record.ready_for_approval,
        "automatic_values": automatic_values,
        "override_fields": override_fields,
        "override_reasons": override_reasons,
        "item_category_options": item_category_options,
        "product_line_options": product_line_options,
        "item_category_option_details": item_category_option_details,
        "product_line_option_details": product_line_option_details,
        **documented_options,
    }


def _lifecycle_payload(item: AnalyzedProduct, masterdata: dict) -> dict:
    return lifecycle_state(item, masterdata).as_dict()


def serialize_ready_product(item: AnalyzedProduct) -> dict:
    proposal = item.proposal
    source = item.source_product



    if proposal is None:
        raise ValueError(
            "READY-produktet mangler ProductProposal."
        )



    masterdata = serialize_masterdata_preview(item)
    return {
        "status": item.status,
        "product_code": source.product_code,
        "ean": source.ean,
        "product_name": source.product_name,
        "product_type": source.product_type,
        "saether_code": source.saether_code,
        "item_number": proposal.item_number,
        "mmstat": proposal.mmstat,
        "item_type": proposal.item_type,
        "brand_code": proposal.brand_code,
        "brand_name": proposal.brand_name,
        "item_group": proposal.item_group,
        "item_class": proposal.item_class,
        "product_line": proposal.product_line,
        "needs_review": list(proposal.needs_review),
        "masterdata": masterdata,
        "lifecycle": _lifecycle_payload(item, masterdata),
        "message": item.message,
    }




def serialize_review_product(item: AnalyzedProduct) -> dict:
    proposal = item.proposal
    source = item.source_product



    if proposal is None:
        raise ValueError(
            "REVIEW-produktet mangler ProductProposal."
        )



    suggestions = get_review_suggestions(proposal)



    masterdata = serialize_masterdata_preview(item)
    return {
        "status": item.status,
        "product_code": source.product_code,
        "ean": source.ean,
        "product_name": source.product_name,
        "product_type": source.product_type,
        "saether_code": source.saether_code,
        "item_number": proposal.item_number,
        "mmstat": proposal.mmstat,
        "item_type": proposal.item_type,
        "brand_code": proposal.brand_code,
        "brand_name": proposal.brand_name,
        "item_group": proposal.item_group,
        "item_class": proposal.item_class,
        "product_line": proposal.product_line,
        "needs_review": list(proposal.needs_review),
        "family_match": (
            item.family_match.status
            if item.family_match
            else None
        ),
        "suggestions": [
            serialize_suggestion(suggestion)
            for suggestion in suggestions
        ],
        "masterdata": masterdata,
        "lifecycle": _lifecycle_payload(item, masterdata),
        "message": item.message,
    }



def serialize_conflict_product(
    item: AnalyzedProduct,
) -> dict:
    source = item.source_product



    golden_record_matches = [
        {
            "item_number": existing.mmitno,
            "ean": existing.ean,
            "product_name": existing.mmitds,
            "item_type": existing.mmity,
            "item_group": existing.mmitgr,
            "item_class": existing.mmitcl,
            "brand_code": existing.mmbuar,
            "brand_name": existing.mmbuartx40,
            "mmstat": existing.mmstat,
            "product_line": existing.mmcfi1tx40,
        }
        for existing in item.existing_products
    ]



    return {
        "status": item.status,
        "lifecycle": lifecycle_state(item).as_dict(),
        "product_code": source.product_code,
        "ean": source.ean,
        "product_name": source.product_name,
        "product_type": source.product_type,
        "saether_code": source.saether_code,
        "message": item.message,
        "golden_record_matches": golden_record_matches,
    }



def serialize_existing_product(item: AnalyzedProduct) -> dict:
    source = item.source_product
    existing_item_number = None



    if item.existing_products:
        existing_item_number = item.existing_products[0].mmitno



    return {
        "status": item.status,
        "lifecycle": lifecycle_state(item).as_dict(),
        "product_code": source.product_code,
        "ean": source.ean,
        "product_name": source.product_name,
        "product_type": source.product_type,
        "existing_item_number": existing_item_number,
        "message": item.message,
    }




def _current_analysis_groups(analysis: ImportAnalysis) -> dict[str, list]:
    """Return live groups even when an older ImportAnalysis stores snapshots."""

    items = None
    for attribute in ("products", "analyzed_products", "items"):
        candidate = getattr(analysis, attribute, None)
        if candidate is not None and not callable(candidate):
            items = list(candidate)
            break
    if items is None:
        items = []
        seen: set[int] = set()
        for attribute in (
            "existing_products",
            "ready_products",
            "review_products",
            "ambiguous_products",
        ):
            for item in getattr(analysis, attribute, ()):
                if id(item) in seen:
                    continue
                seen.add(id(item))
                items.append(item)

    groups = {"EXISTING": [], "READY": [], "REVIEW": [], "AMBIGUOUS": []}
    for item in items:
        status = str(getattr(item, "status", "")).strip().upper()
        if status in groups:
            groups[status].append(item)
    return groups


def serialize_analysis(
    analysis_id: str,
    analysis: ImportAnalysis,
) -> dict:
    brand_rule = (
        analysis.brand_rule_resolution.rule
        if analysis.brand_rule_resolution
        else None
    )



    groups = _current_analysis_groups(analysis)
    live_existing = groups["EXISTING"]
    live_ready = groups["READY"]
    live_review = groups["REVIEW"]
    live_ambiguous = groups["AMBIGUOUS"]

    existing_products = [
        serialize_existing_product(item)
        for item in live_existing
    ]



    conflict_products = [
        serialize_conflict_product(item)
        for item in live_ambiguous
    ]



    approved_batch = approved_batches.get(analysis_id)
    verification_prepared = analysis_id in verification_batches
    approval_completed = approved_batch is not None
    try:
        brand_options = get_classification_registry().brand_options()
    except ValueError:
        brand_options = []

    ready_products = [serialize_ready_product(item) for item in live_ready]
    review_products = [serialize_review_product(item) for item in live_review]
    lifecycle_counts: dict[str, int] = {}
    for product in [*ready_products, *review_products, *conflict_products]:
        stage = str((product.get("lifecycle") or {}).get("stage") or "ANALYSIS")
        lifecycle_counts[stage] = lifecycle_counts.get(stage, 0) + 1

    return {
        "analysis_id": analysis_id,
        "source_file": analysis.source_file,
        "total": analysis.total_products,
        "existing": len(live_existing),
        "ready": len(live_ready),
        "review": len(live_review),
        "ambiguous": len(live_ambiguous),
        "identifier_conflicts": len(
            analysis.identifier_conflicts
        ),
        "brand": {
            "status": analysis.brand_resolution.status,
            "code": analysis.brand_resolution.brand_code,
            "name": analysis.brand_resolution.brand_name,
            "generation_prefix_status": (
                analysis.brand_rule_resolution.status
                if analysis.brand_rule_resolution
                else None
            ),
            "generation_prefix": (
                brand_rule.generation_prefix
                if brand_rule
                else None
            ),
        },
        "brand_options": brand_options,
        "ready_products": ready_products,
        "review_products": review_products,
        "existing_products": existing_products,
        "conflict_products": conflict_products,
        "lifecycle_counts": lifecycle_counts,
        "code_reservations": list(
            code_reservation_batches.get(analysis_id, {}).values()
        ),
        "verification_prepared": verification_prepared,
        "approval_completed": approval_completed,
        "workflow": {
            "current_step": (
                "approved"
                if approval_completed
                else "verification"
                if verification_prepared
                else "masterdata_review"
                if lifecycle_counts.get("MASTERDATA_REVIEW")
                else "code_ready"
                if lifecycle_counts.get("CODE_READY")
                else "identity_review"
                if lifecycle_counts.get("IDENTITY_REVIEW")
                else "analysis"
            ),
            "verification_available": bool(
                lifecycle_counts.get("READY_FOR_APPROVAL")
            ),
            "code_reservation_available": bool(
                lifecycle_counts.get("CODE_READY")
            ),
            "approval_available": verification_prepared,
            "masterdata_download_available": bool(
                approved_batch
                and approved_batch.ready_for_m3
                and approved_batch.approved_count > 0
            ),
        },
    }




# ---------------------------------------------------------
# VERIFICATION SERIALIZATION
# ---------------------------------------------------------




def serialize_verification_item(
    item: VerificationItem,
    *,
    analysis_id: str | None = None,
) -> dict:
    masterdata = None
    if analysis_id is not None:
        analysis = analysis_sessions.get(analysis_id)
        if analysis is not None:
            analyzed = find_analyzed_product(analysis, item.product_key)
            if analyzed is not None:
                masterdata = serialize_masterdata_preview(analyzed)

    return {
        "product_key": item.product_key,
        "product_code": item.product_code,
        "ean": item.ean,
        "product_name": item.product_name,
        "status": item.status,
        "item_number": item.item_number,
        "incoming_saether_code": item.incoming_saether_code,
        "mmstat": item.mmstat,
        "item_type": item.item_type,
        "brand_code": item.brand_code,
        "brand_name": item.brand_name,
        "item_group": item.item_group,
        "item_class": item.item_class,
        "product_line": item.product_line,
        "masterdata": masterdata,
        "errors": list(item.errors),
        "warnings": list(item.warnings),
    }




def serialize_verification_batch(
    batch: VerificationBatch,
) -> dict:
    return {
        "analysis_id": batch.analysis_id,
        "requested_count": batch.requested_count,
        "prepared_count": batch.prepared_count,
        "blocked_count": batch.blocked_count,
        "can_continue": batch.can_continue,
        "items": [
            serialize_verification_item(
                item,
                analysis_id=batch.analysis_id,
            )
            for item in batch.items
        ],
    }




# ---------------------------------------------------------
# APPROVAL SERIALIZATION
# ---------------------------------------------------------




def serialize_approval_item(item: ApprovalItem) -> dict:
    return {
        "product_key": item.product_key,
        "product_code": item.product_code,
        "ean": item.ean,
        "product_name": item.product_name,
        "item_number": item.item_number,
        "status": item.status,
        "approved_at": item.approved_at,
        "approval_source": item.approval_source,
        "errors": list(item.errors),
    }




def serialize_approval_batch(batch: ApprovalBatch) -> dict:
    return {
        "analysis_id": batch.analysis_id,
        "requested_count": batch.requested_count,
        "approved_count": batch.approved_count,
        "blocked_count": batch.blocked_count,
        "ready_for_m3": batch.ready_for_m3,
        "items": [
            serialize_approval_item(item)
            for item in batch.items
        ],
    }




# ---------------------------------------------------------
# PRODUCT LOOKUP
# ---------------------------------------------------------




def find_analyzed_product(
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




# ---------------------------------------------------------
# ANALYZE / GET ANALYSIS
# ---------------------------------------------------------




@app.post("/analyze")
def analyze(file: UploadFile = File(...)) -> dict:
    if golden_record is None:
        raise HTTPException(
            status_code=503,
            detail="Golden Record er ikke indlæst.",
        )



    filename = Path(file.filename or "upload.xlsx").name



    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Kun .xlsx-filer understøttes.",
        )



    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / filename



        with temp_path.open("wb") as output:
            shutil.copyfileobj(file.file, output)



        try:
            analysis = analyze_import(
                temp_path,
                golden_record,
            )
        except Exception as error:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Excel-filen kunne ikke analyseres: "
                    f"{error}"
                ),
            ) from error



    analysis_id = str(uuid.uuid4())
    analysis_sessions[analysis_id] = analysis



    return serialize_analysis(
        analysis_id=analysis_id,
        analysis=analysis,
    )




@app.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str) -> dict:
    analysis = analysis_sessions.get(analysis_id)



    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Analysen blev ikke fundet. "
                "Den kan være udløbet efter en "
                "genstart af backend."
            ),
        )



    return serialize_analysis(
        analysis_id=analysis_id,
        analysis=analysis,
    )




# ---------------------------------------------------------
# REVIEW
# ---------------------------------------------------------




def _set_proposal_brand(proposal, brand_code: str, brand_name: str) -> None:
    try:
        setattr(proposal, "brand_code", brand_code)
        setattr(proposal, "brand_name", brand_name)
    except (AttributeError, TypeError) as error:
        raise ValueError(
            "ProductProposal kan ikke gemme det valgte brand."
        ) from error


def _sync_proposal_review_fields(proposal, blocking_fields: list[str]) -> None:
    """Keep the legacy proposal gate aligned with the rebuilt preview gate."""

    if not hasattr(proposal, "needs_review"):
        return
    legacy_names = {"product_group": "item_class"}
    normalized = tuple(
        dict.fromkeys(legacy_names.get(field, field) for field in blocking_fields)
    )
    try:
        setattr(proposal, "needs_review", normalized)
    except (AttributeError, TypeError):
        # The rebuilt preview remains authoritative for immutable old proposals.
        return


def _sync_analysis_status_collections(
    analysis: ImportAnalysis,
    item: AnalyzedProduct,
) -> None:
    """Move an item between mutable legacy snapshot lists when they exist."""

    attributes = {
        "EXISTING": "existing_products",
        "READY": "ready_products",
        "REVIEW": "review_products",
        "AMBIGUOUS": "ambiguous_products",
    }
    for attribute in attributes.values():
        collection = getattr(analysis, attribute, None)
        if isinstance(collection, list):
            collection[:] = [candidate for candidate in collection if candidate is not item]
    target = getattr(
        analysis,
        attributes.get(str(getattr(item, "status", "")).upper(), ""),
        None,
    )
    if isinstance(target, list) and item not in target:
        target.append(item)


@app.post("/reviews/{analysis_id}/{product_key}")
def review_product(
    analysis_id: str,
    product_key: str,
    request: ReviewRequest,
) -> dict:
    analysis = analysis_sessions.get(analysis_id)



    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Analysen blev ikke fundet. "
                "Upload og analysér filen igen."
            ),
        )



    analyzed_product = find_analyzed_product(
        analysis=analysis,
        product_key=product_key,
    )



    if analyzed_product is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Produkt {product_key} blev ikke "
                "fundet i analysen."
            ),
        )



    if analyzed_product.status == "EXISTING":
        raise HTTPException(
            status_code=400,
            detail=(
                "Eksisterende M3-produkter kan "
                "ikke ændres gennem review."
            ),
        )



    if analyzed_product.status == "AMBIGUOUS":
        raise HTTPException(
            status_code=400,
            detail=(
                "Produktet har et tvetydigt EAN-match "
                "og skal afklares før review."
            ),
        )



    proposal = analyzed_product.proposal



    if proposal is None:
        raise HTTPException(
            status_code=400,
            detail="Produktet mangler et ProductProposal.",
        )


    requested_brand_code = (
        str(request.brand_code).strip()
        if request.brand_code is not None
        else None
    )
    requested_brand_name = (
        " ".join(str(request.brand_name).split())
        if request.brand_name is not None
        else None
    )
    if bool(requested_brand_code) != bool(requested_brand_name):
        raise HTTPException(
            status_code=400,
            detail="Vælg både brandkode og brandnavn fra den dokumenterede liste.",
        )

    brand_changed = False
    if requested_brand_code and requested_brand_name:
        if any(
            value is not None and str(value).strip()
            for value in (
                request.item_group,
                request.item_class,
                request.product_line,
                request.item_category,
            )
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Vælg brand først. Backend skal genklassificere produktet "
                    "før MMITGR, MMITCL, Product line eller Item category vælges."
                ),
            )
        try:
            registry = get_classification_registry()
        except ValueError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if not registry.has_brand(requested_brand_code, requested_brand_name):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Brand skal vælges som et observeret MMBUAR/MMBUARTX40-par "
                    "fra Golden Record."
                ),
            )
        try:
            _set_proposal_brand(
                proposal,
                requested_brand_code,
                requested_brand_name,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        brand_changed = True



    feedback_values = {
        "item_type": request.item_type,
        "item_group": request.item_group,
        "item_class": request.item_class,
        "product_line": request.product_line,
    }
    supplied_feedback = {
        field_name: str(value).strip()
        for field_name, value in feedback_values.items()
        if value is not None and str(value).strip()
    }
    if request.masterdata_review:
        # MASTERDATA overrides belong to the downstream review layer.  They must
        # not rewrite the SKU proposal that produced the automatic evidence.
        supplied_feedback = {}
    masterdata_values = {
        "m3_name": request.m3_name,
        "m3_description": request.m3_description,
        "receipt_text": request.receipt_text,
        "item_group": request.item_group,
        "product_group": request.item_class,
        "product_line": request.product_line,
        "item_category": request.item_category,
        "item_group_description": request.item_group_description,
    }
    supplied_masterdata = {
        field_name: str(value).strip()
        for field_name, value in masterdata_values.items()
        if value is not None and str(value).strip()
    }
    if request.is_new_item_group is not None:
        supplied_masterdata["is_new_item_group"] = (
            request.is_new_item_group
        )

    override_fields = set(request.override_fields)
    reset_override_fields = set(request.reset_override_fields)
    invalid_override_fields = (
        override_fields | reset_override_fields
    ) - AUTOMATIC_MASTERDATA_FIELDS
    if invalid_override_fields:
        raise HTTPException(
            status_code=400,
            detail=(
                "Ukendte override-felter: "
                + ", ".join(sorted(invalid_override_fields))
            ),
        )

    if (
        not brand_changed
        and not supplied_feedback
        and not supplied_masterdata
        and not reset_override_fields
    ):
        raise HTTPException(
            status_code=400,
            detail="Review indeholder ingen ændringer.",
        )

    preview_before = serialize_masterdata_preview(analyzed_product)
    existing_review = _masterdata_review_values(analyzed_product)

    if override_fields and not (request.override_reason or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Angiv en begrundelse for den manuelle overstyring.",
        )

    if request.masterdata_review:
        for field_name in AUTOMATIC_MASTERDATA_FIELDS:
            if field_name not in supplied_masterdata:
                continue
            automatic_value = (
                preview_before.get("automatic_values") or {}
            ).get(field_name)
            already_overridden = field_name in (
                preview_before.get("override_fields") or []
            )
            if (
                automatic_value is not None or already_overridden
            ) and field_name not in override_fields:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{field_name} er automatisk afledt. "
                        "Vælg Overstyr og angiv en begrundelse."
                    ),
                )

    try:
        reference = get_masterdata_reference()
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    selected_brand_code = getattr(proposal, "brand_code", None)
    selected_brand_name = getattr(proposal, "brand_name", None)
    classification_values_requested = bool(
        request.item_group and str(request.item_group).strip()
        or request.item_class and str(request.item_class).strip()
    )
    if classification_values_requested and not (
        selected_brand_code and selected_brand_name
    ):
        raise HTTPException(
            status_code=400,
            detail="Vælg brand før dokumenterede MMITGR/MMITCL-værdier.",
        )

    option_payload = get_classification_registry().classification_options(
        brand_code=selected_brand_code,
        brand_name=selected_brand_name,
        source_product=analyzed_product.source_product,
        proposal=proposal,
        selected_item_group=request.item_group or getattr(
            proposal, "item_group", None
        ),
    )
    if request.item_group and str(request.item_group).strip():
        allowed_item_groups = {
            str(option["value"])
            for option in option_payload["item_group_options"]
        }
        if str(request.item_group).strip() not in allowed_item_groups:
            raise HTTPException(
                status_code=400,
                detail=(
                    "MMITGR skal vælges fra dokumenterede Golden Record-værdier "
                    "for det valgte brand."
                ),
            )
    if request.item_class and str(request.item_class).strip():
        allowed_item_classes = {
            str(option["value"])
            for option in option_payload["item_class_options"]
        }
        if str(request.item_class).strip() not in allowed_item_classes:
            raise HTTPException(
                status_code=400,
                detail=(
                    "MMITCL skal vælges fra dokumenterede Golden Record-værdier "
                    "for det valgte brand og den relevante familie."
                ),
            )

    if request.item_category is not None and not request.masterdata_review:
        raise HTTPException(
            status_code=400,
            detail="Item category skal gemmes gennem MASTERDATA-review.",
        )
    if "item_category" in supplied_masterdata:
        allowed_categories = {
            item.combined for item in reference.item_categories
        }
        if supplied_masterdata["item_category"] not in allowed_categories:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Item category skal vælges fra 'Data for drop downs' "
                    "i den aktive MASTERDATA-template."
                ),
            )
    if "product_line" in supplied_masterdata or "product_line" in supplied_feedback:
        allowed_product_lines = {
            item.export_code for item in reference.product_lines
        }
        selected_product_line = (
            supplied_masterdata.get("product_line")
            or supplied_feedback.get("product_line")
        )
        if (
            allowed_product_lines
            and selected_product_line not in allowed_product_lines
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Product line skal vælges fra den aktive "
                    "MASTERDATA-template."
                ),
            )

    limits = {
        "m3_name": 30,
        "m3_description": 60,
        "receipt_text": 20,
        "item_group_description": 40,
    }
    for field_name, limit in limits.items():
        value = supplied_masterdata.get(field_name)
        if value is not None and len(str(value)) > limit:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{field_name} må højst være {limit} tegn."
                ),
            )

    saved_feedback = []
    result = None
    try:
        if supplied_feedback:
            result = apply_review(
                proposal=proposal,
                changes=ReviewChanges(
                    item_type=request.item_type,
                    item_group=request.item_group,
                    item_class=request.item_class,
                    product_line=request.product_line,
                ),
            )
            for field_name in result.changed_fields:
                selected_value = supplied_feedback.get(field_name)
                if selected_value is not None:
                    saved_feedback.append(
                        save_feedback(
                            proposal=proposal,
                            field_name=field_name,
                            selected_value=selected_value,
                        )
                    )

        if supplied_masterdata or reset_override_fields:
            merged = dict(existing_review)
            automatic_values = dict(
                merged.get("__automatic_values") or {}
            )
            override_reasons = dict(
                merged.get("__override_reasons") or {}
            )

            for field_name in reset_override_fields:
                merged.pop(field_name, None)
                automatic_values.pop(field_name, None)
                override_reasons.pop(field_name, None)

            for field_name in override_fields:
                if field_name in supplied_masterdata:
                    automatic_values.setdefault(
                        field_name,
                        (preview_before.get("automatic_values") or {}).get(
                            field_name
                        ),
                    )
                    override_reasons[field_name] = (
                        request.override_reason or ""
                    ).strip()

            merged.update(supplied_masterdata)
            if automatic_values:
                merged["__automatic_values"] = automatic_values
            else:
                merged.pop("__automatic_values", None)
            if override_reasons:
                merged["__override_reasons"] = override_reasons
            else:
                merged.pop("__override_reasons", None)
            _save_masterdata_review_values(analyzed_product, merged)
    except (AttributeError, TypeError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    preview_after = serialize_masterdata_preview(analyzed_product)
    blocking_after = list(preview_after.get("blocking_fields") or [])
    _sync_proposal_review_fields(proposal, blocking_after)
    if (
        "error" not in preview_after
        and preview_after.get("ready_for_verification") is True
        and not blocking_after
    ):
        analyzed_product.status = "READY"
        analyzed_product.message = (
            "Alle blokerende minimumskrav er dokumenteret. "
            "Produktet er flyttet til Klar og kan verificeres."
        )
    else:
        analyzed_product.status = "REVIEW"
        analyzed_product.message = (
            "Review er gemt, men produktet forbliver i REVIEW, "
            "indtil alle blokerende minimumskrav er dokumenteret."
        )
    _sync_analysis_status_collections(analysis, analyzed_product)

    changed_fields = [
        *(["brand_code", "brand_name"] if brand_changed else []),
        *supplied_masterdata,
        *(f"reset:{field_name}" for field_name in sorted(reset_override_fields)),
    ]
    if result is not None:
        changed_fields = list(dict.fromkeys(
            [*result.changed_fields, *changed_fields]
        ))
    ready = analyzed_product.status == "READY"

    # A changed review invalidates only the prepared/approved snapshots.  The
    # reservation layer remains untouched, so preparing again reuses the
    # existing Sæther Code while forcing verification of the refreshed values.
    verification_batches.pop(analysis_id, None)
    approved_batches.pop(analysis_id, None)

    serialized_product = (
        serialize_ready_product(analyzed_product)
        if analyzed_product.status == "READY"
        else serialize_review_product(analyzed_product)
    )
    review_summary = summarize_masterdata_review(
        serialized_product.get("masterdata") or {},
        changed_fields=changed_fields,
    )

    return {
        "analysis_id": analysis_id,
        "saved_feedback": saved_feedback,
        "product": serialized_product,
        "changed_fields": changed_fields,
        "ready": ready,
        "review_summary": review_summary,
        "analysis": serialize_analysis(
            analysis_id=analysis_id,
            analysis=analysis,
        ),
    }




# ---------------------------------------------------------
# RESERVE SÆTHER CODE BEFORE MASTERDATA COMPLETION
# ---------------------------------------------------------


def _reserve_code_for_item(
    *,
    analysis_id: str,
    analysis: ImportAnalysis,
    item: AnalyzedProduct,
    product_key: str,
) -> dict:
    proposal = getattr(item, "proposal", None)
    if proposal is None:
        raise ValueError("Produktet mangler ProductProposal.")

    preview_before = serialize_masterdata_preview(item)
    state_before = lifecycle_state(item, preview_before)
    existing_number = getattr(proposal, "item_number", None)
    if existing_number:
        return {
            "product_key": product_key,
            "item_number": str(existing_number),
            "status": "RESERVED",
            "reused": True,
        }
    if state_before.stage != CODE_READY:
        blockers = ", ".join(state_before.blockers) or state_before.label
        raise ValueError(
            "Sæther Code kan ikke reserveres endnu. Blokerer: " + blockers
        )

    # Reuse the established uniqueness/reservation service.  It historically
    # expected READY, even though code reservation now happens before complete
    # MASTERDATA.  The temporary state is restored in all cases; no review tuple
    # is mutated in place.
    original_status = getattr(item, "status", None)
    had_needs_review = hasattr(proposal, "needs_review")
    original_needs_review = getattr(proposal, "needs_review", ())
    try:
        item.status = "READY"
        if had_needs_review:
            setattr(proposal, "needs_review", ())
        batch = prepare_verification_batch(
            analysis_id=analysis_id,
            products=[item],
            golden_record=golden_record,
        )
    finally:
        item.status = original_status
        if had_needs_review:
            setattr(proposal, "needs_review", original_needs_review)

    prepared_item = next(
        (
            candidate
            for candidate in getattr(batch, "items", ())
            if getattr(candidate, "product_key", None) == product_key
        ),
        None,
    )
    if prepared_item is None:
        raise ValueError("Reservationsservicen returnerede ikke produktet.")
    if str(getattr(prepared_item, "status", "")).upper() != "PREPARED":
        errors = ", ".join(getattr(prepared_item, "errors", ()) or ())
        raise ValueError(errors or "Sæther Code kunne ikke reserveres.")

    item_number = getattr(prepared_item, "item_number", None) or getattr(
        proposal, "item_number", None
    )
    if not item_number:
        raise ValueError("Reservationsservicen returnerede ingen Sæther Code.")
    setattr(proposal, "item_number", str(item_number))
    return {
        "product_key": product_key,
        "item_number": str(item_number),
        "status": "RESERVED",
        "reused": False,
    }


@app.post("/analyses/{analysis_id}/reserve-codes")
def reserve_codes(
    analysis_id: str,
    request: ReserveCodeRequest,
) -> dict:
    if golden_record is None:
        raise HTTPException(status_code=503, detail="Golden Record er ikke indlæst.")
    analysis = analysis_sessions.get(analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysen blev ikke fundet.")
    if not request.product_keys:
        raise HTTPException(status_code=400, detail="Vælg mindst ét produkt.")

    reservations = code_reservation_batches.setdefault(analysis_id, {})
    results: list[dict] = []
    for raw_key in dict.fromkeys(request.product_keys):
        product_key = str(raw_key).strip()
        item = find_analyzed_product(analysis, product_key)
        if item is None:
            results.append({
                "product_key": product_key,
                "status": "BLOCKED",
                "errors": ["Produktet blev ikke fundet i analysen."],
            })
            continue
        try:
            result = _reserve_code_for_item(
                analysis_id=analysis_id,
                analysis=analysis,
                item=item,
                product_key=product_key,
            )
        except ValueError as error:
            results.append({
                "product_key": product_key,
                "status": "BLOCKED",
                "errors": [str(error)],
            })
            continue

        reservations[product_key] = result
        preview_after = serialize_masterdata_preview(item)
        state_after = lifecycle_state(item, preview_after)
        if state_after.stage == READY_FOR_APPROVAL:
            item.status = "READY"
            item.message = "Sæther Code er reserveret, og MASTERDATA er klar til godkendelse."
        else:
            item.status = "REVIEW"
            item.message = (
                "Sæther Code er reserveret. Færdiggør kun de resterende "
                "påkrævede MASTERDATA-felter."
            )
        _sync_analysis_status_collections(analysis, item)
        result = {
            **result,
            "lifecycle": lifecycle_state(item, preview_after).as_dict(),
        }
        reservations[product_key] = result
        results.append(result)

    verification_batches.pop(analysis_id, None)
    approved_batches.pop(analysis_id, None)
    return {
        "analysis_id": analysis_id,
        "reservations": results,
        "reserved_count": sum(item["status"] == "RESERVED" for item in results),
        "blocked_count": sum(item["status"] == "BLOCKED" for item in results),
        "analysis": serialize_analysis(analysis_id=analysis_id, analysis=analysis),
    }


# ---------------------------------------------------------
# PREPARE / GET VERIFICATION
# ---------------------------------------------------------




@app.post("/analyses/{analysis_id}/prepare")
def prepare_analysis(
    analysis_id: str,
    request: PrepareRequest,
) -> dict:
    if golden_record is None:
        raise HTTPException(
            status_code=503,
            detail="Golden Record er ikke indlæst.",
        )



    analysis = analysis_sessions.get(analysis_id)



    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Analysen blev ikke fundet. "
                "Upload og analysér filen igen."
            ),
        )



    if not request.product_keys:
        raise HTTPException(
            status_code=400,
            detail="Vælg mindst ét produkt til verificering.",
        )

    missing_reservations = []
    for product_key in request.product_keys:
        selected = find_analyzed_product(
            analysis,
            product_key,
        )
        proposal = (
            getattr(selected, "proposal", None)
            if selected
            else None
        )
        if not getattr(proposal, "item_number", None):
            missing_reservations.append(str(product_key))

    if missing_reservations:
        raise HTTPException(
            status_code=409,
            detail=(
                "Reservér Sæther Code før verificering: "
                + ", ".join(missing_reservations)
            ),
        )

    products = []
    for product_key in request.product_keys:
        selected = find_analyzed_product(
            analysis,
            str(product_key).strip(),
        )

        if selected is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Produktet {product_key} blev ikke fundet "
                    "i analysen."
                ),
            )

        products.append(selected)

    try:
        batch = prepare_verification_batch(
            analysis_id=analysis_id,
            products=products,
            golden_record=golden_record,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "Produkterne kunne ikke "
                "forberedes til verificering: "
                f"{error}"
            ),
        ) from error


    verification_batches[analysis_id] = batch
    approved_batches.pop(analysis_id, None)



    return {
        "verification": serialize_verification_batch(batch),
        "analysis": serialize_analysis(
            analysis_id=analysis_id,
            analysis=analysis,
        ),
    }




@app.get("/analyses/{analysis_id}/verification")
def get_verification(analysis_id: str) -> dict:
    if analysis_id not in analysis_sessions:
        raise HTTPException(
            status_code=404,
            detail=(
                "Analysen blev ikke fundet. "
                "Upload og analysér filen igen."
            ),
        )



    batch = verification_batches.get(analysis_id)



    if batch is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Der er endnu ikke forberedt "
                "produkter til verificering."
            ),
        )



    return serialize_verification_batch(batch)




# ---------------------------------------------------------
# APPROVE / GET APPROVAL
# ---------------------------------------------------------




@app.post("/analyses/{analysis_id}/approve")
def approve_analysis(
    analysis_id: str,
    request: ApproveRequest,
) -> dict:
    if golden_record is None:
        raise HTTPException(
            status_code=503,
            detail="Golden Record er ikke indlæst.",
        )



    if request.confirmed is not True:
        raise HTTPException(
            status_code=400,
            detail=(
                "Approval kræver eksplicit "
                "brugergodkendelse."
            ),
        )



    analysis = analysis_sessions.get(analysis_id)



    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Analysen blev ikke fundet. "
                "Upload og analysér filen igen."
            ),
        )



    verification = verification_batches.get(analysis_id)



    if verification is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Produkterne skal forberedes og "
                "verificeres før godkendelse."
            ),
        )



    approval_items: list[ApprovalItem] = []
    approved_products: list[ApprovedProduct] = []
    masterdata_builder = get_masterdata_builder()



    for verification_item in verification.items:
        analyzed_product = find_analyzed_product(
            analysis=analysis,
            product_key=verification_item.product_key,
        )



        base_item = ApprovalItem(
            product_key=verification_item.product_key,
            product_code=verification_item.product_code,
            ean=verification_item.ean,
            product_name=verification_item.product_name,
            item_number=verification_item.item_number,
            status="BLOCKED",
        )



        if verification_item.status != "PREPARED":
            base_item.errors.append(
                "Produktet har ikke status PREPARED."
            )
            approval_items.append(base_item)
            continue



        if analyzed_product is None:
            base_item.errors.append(
                "Produktet blev ikke fundet i analysen."
            )
            approval_items.append(base_item)
            continue



        proposal = analyzed_product.proposal



        if proposal is None:
            base_item.errors.append(
                "Produktet mangler ProductProposal."
            )
            approval_items.append(base_item)
            continue

        try:
            masterdata_preview = masterdata_builder.build_preview(
                analyzed_product
            )
        except (FileNotFoundError, ValueError) as error:
            base_item.errors.append(f"MASTERDATA kunne ikke valideres: {error}")
            approval_items.append(base_item)
            continue

        if masterdata_preview.missing_required_fields:
            base_item.errors.append(
                "Mangler krævede MASTERDATA-felter: "
                + ", ".join(masterdata_preview.missing_required_fields)
            )
            approval_items.append(base_item)
            continue



        try:
            approved_product = approve_product(
                proposal=proposal,
                source_product=analyzed_product.source_product,
                golden_record=golden_record,
                confirmed=True,
            )
        except ValueError as error:
            base_item.errors.append(str(error))
            approval_items.append(base_item)
            continue
        except Exception as error:
            base_item.errors.append(
                f"Uventet approval-fejl: {error}"
            )
            approval_items.append(base_item)
            continue



        approved_products.append(approved_product)
        approval_items.append(
            ApprovalItem(
                product_key=verification_item.product_key,
                product_code=verification_item.product_code,
                ean=verification_item.ean,
                product_name=verification_item.product_name,
                item_number=proposal.item_number,
                status="APPROVED",
                approved_at=approved_product.approved_at,
                approval_source=(
                    approved_product.approval_source
                ),
            )
        )



    approved_count = sum(
        item.status == "APPROVED"
        for item in approval_items
    )
    blocked_count = sum(
        item.status == "BLOCKED"
        for item in approval_items
    )



    batch = ApprovalBatch(
        analysis_id=analysis_id,
        requested_count=len(verification.items),
        approved_count=approved_count,
        blocked_count=blocked_count,
        items=approval_items,
        approved_products=approved_products,
    )



    approved_batches[analysis_id] = batch



    return {
        "approval": serialize_approval_batch(batch),
        "verification": serialize_verification_batch(
            verification
        ),
        "analysis": serialize_analysis(
            analysis_id=analysis_id,
            analysis=analysis,
        ),
    }




@app.get("/analyses/{analysis_id}/approval")
def get_approval(analysis_id: str) -> dict:
    if analysis_id not in analysis_sessions:
        raise HTTPException(
            status_code=404,
            detail=(
                "Analysen blev ikke fundet. "
                "Upload og analysér filen igen."
            ),
        )



    batch = approved_batches.get(analysis_id)



    if batch is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Der er endnu ikke godkendt "
                "produkter i analysen."
            ),
        )



    return serialize_approval_batch(batch)




# ---------------------------------------------------------
# MASTERDATA EXPORT
# ---------------------------------------------------------




@app.get("/analyses/{analysis_id}/masterdata.xlsx")
def download_masterdata(analysis_id: str) -> FileResponse:
    batch = approved_batches.get(analysis_id)



    if batch is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Der findes ingen godkendt batch for analysen. "
                "Produkterne skal godkendes før MASTERDATA-eksport."
            ),
        )



    approved_products = list(batch.approved_products)



    if not approved_products:
        raise HTTPException(
            status_code=409,
            detail=(
                "Der er ingen godkendte produkter til "
                "MASTERDATA-eksport."
            ),
        )



    try:
        records = get_masterdata_builder().build_many(approved_products)
    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        ) from error



    temporary_file = tempfile.NamedTemporaryFile(
        prefix="MASTERDATA_",
        suffix=".xlsx",
        delete=False,
    )
    temporary_path = Path(temporary_file.name)
    temporary_file.close()



    try:
        MasterDataExcelExporter(
            template_path=MASTERDATA_TEMPLATE_PATH
        ).export(
            records=records,
            output_path=temporary_path,
        )
    except (FileNotFoundError, ValueError) as error:
        temporary_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=409,
            detail=str(error),
        ) from error
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise



    return FileResponse(
        path=temporary_path,
        media_type=MASTERDATA_MEDIA_TYPE,
        filename=f"MASTERDATA_{analysis_id}.xlsx",
        background=BackgroundTask(
            temporary_path.unlink,
            missing_ok=True,
        ),
    )
