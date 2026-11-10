import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path



from fastapi import (
    FastAPI,
    File,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel



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




app = FastAPI(
    title="Sæther Masterdata Automation",
    version="0.6.0",
)




golden_record: GoldenRecord | None = None




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




# ---------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------




class ReviewRequest(BaseModel):
    item_type: str | None = None
    item_group: str | None = None
    item_class: str | None = None
    product_line: str | None = None




class PrepareRequest(BaseModel):
    product_keys: list[str]




class ApproveRequest(BaseModel):
    confirmed: bool = False




# ---------------------------------------------------------
# STARTUP / HEALTH
# ---------------------------------------------------------




@app.on_event("startup")
def startup() -> None:
    global golden_record



    print("Indlæser Golden Record...")
    golden_record = GoldenRecord().load()
    print(
        f"Golden Record klar: "
        f"{len(golden_record):,} produkter"
    )




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
    }




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




def serialize_ready_product(item: AnalyzedProduct) -> dict:
    proposal = item.proposal
    source = item.source_product



    if proposal is None:
        raise ValueError(
            "READY-produktet mangler ProductProposal."
        )



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
        "product_code": source.product_code,
        "ean": source.ean,
        "product_name": source.product_name,
        "product_type": source.product_type,
        "existing_item_number": existing_item_number,
        "message": item.message,
    }




def serialize_analysis(
    analysis_id: str,
    analysis: ImportAnalysis,
) -> dict:
    brand_rule = (
        analysis.brand_rule_resolution.rule
        if analysis.brand_rule_resolution
        else None
    )



    existing_products = [
        serialize_existing_product(item)
        for item in analysis.existing_products
    ]



    conflict_products = [
        serialize_conflict_product(item)
        for item in analysis.ambiguous_products
    ]



    return {
        "analysis_id": analysis_id,
        "source_file": analysis.source_file,
        "total": analysis.total_products,
        "existing": len(analysis.existing_products),
        "ready": len(analysis.ready_products),
        "review": len(analysis.review_products),
        "ambiguous": len(analysis.ambiguous_products),
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
        "ready_products": [
            serialize_ready_product(item)
            for item in analysis.ready_products
        ],
        "review_products": [
            serialize_review_product(item)
            for item in analysis.review_products
        ],
        "existing_products": existing_products,
        "conflict_products": conflict_products,
        "verification_prepared": (
            analysis_id in verification_batches
        ),
        "approval_completed": (
            analysis_id in approved_batches
        ),
    }




# ---------------------------------------------------------
# VERIFICATION SERIALIZATION
# ---------------------------------------------------------




def serialize_verification_item(
    item: VerificationItem,
) -> dict:
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
            serialize_verification_item(item)
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



    feedback_values = {
        "item_type": request.item_type,
        "item_group": request.item_group,
        "item_class": request.item_class,
        "product_line": request.product_line,
    }



    supplied_values = {
        field_name: str(value).strip()
        for field_name, value in feedback_values.items()
        if value is not None and str(value).strip()
    }



    if not supplied_values:
        raise HTTPException(
            status_code=400,
            detail="Review indeholder ingen ændringer.",
        )



    try:
        result = apply_review(
            proposal=proposal,
            changes=ReviewChanges(
                item_type=request.item_type,
                item_group=request.item_group,
                item_class=request.item_class,
                product_line=request.product_line,
            ),
        )



        saved_feedback = []



        for field_name in result.changed_fields:
            selected_value = supplied_values.get(field_name)



            if selected_value is None:
                continue



            saved_feedback.append(
                save_feedback(
                    proposal=proposal,
                    field_name=field_name,
                    selected_value=selected_value,
                )
            )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error



    if result.ready:
        analyzed_product.status = "READY"
        analyzed_product.message = (
            "Brugerreview er afsluttet. "
            "Produktet er klar til MMITNO-generering."
        )
    else:
        analyzed_product.status = "REVIEW"
        analyzed_product.message = (
            "Brugerreview er gemt, men produktet "
            "mangler stadig obligatoriske felter."
        )



    return {
        "analysis_id": analysis_id,
        "saved_feedback": saved_feedback,
        "product": (
            serialize_ready_product(analyzed_product)
            if analyzed_product.status == "READY"
            else serialize_review_product(analyzed_product)
        ),
        "changed_fields": result.changed_fields,
        "ready": result.ready,
        "analysis": serialize_analysis(
            analysis_id=analysis_id,
            analysis=analysis,
        ),
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



    try:
        batch = prepare_verification_batch(
            analysis_id=analysis_id,
            analysis=analysis,
            product_keys=request.product_keys,
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
            approved_product = approve_product(
                proposal=proposal,
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
