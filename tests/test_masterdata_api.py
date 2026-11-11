from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from app import web


@dataclass
class SourceProduct:
    product_code: str
    product_name: str
    ean: str
    m3_description: str | None = None
    receipt_text: str | None = None


@dataclass
class ProductProposal:
    item_number: str | None
    item_type: str
    item_group: str
    item_class: str
    brand_code: str
    brand_name: str


@dataclass
class ApprovedProduct:
    source_product: SourceProduct
    proposal: ProductProposal
    status: str = "APPROVED"


@dataclass
class GoldenRecordProduct:
    mmitno: str
    mmitds: str
    mmfuds: str
    mmity: str
    mmitgr: str
    mmitgrtx40: str
    mmitcl: str
    mmitcltx40: str
    mmbuar: str
    mmbuartx40: str
    mmcfi1: str
    mmcfi1tx40: str
    supplier_item_number: str
    receipt_text: str
    mmstat: str = "20"


@dataclass
class FakeGoldenRecord:
    products: list[GoldenRecordProduct]


@pytest.fixture(autouse=True)
def clear_batches() -> None:
    previous = web.golden_record
    web.analysis_sessions.clear()
    web.verification_batches.clear()
    web.approved_batches.clear()
    yield
    web.analysis_sessions.clear()
    web.verification_batches.clear()
    web.approved_batches.clear()
    web.golden_record = previous


@pytest.fixture
def client() -> TestClient:
    return TestClient(web.app)


@pytest.fixture
def template_path(tmp_path: Path) -> Path:
    path = tmp_path / "saether_masterdata_template.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Master template"
    for name in ("Product line", "Data for drop downs", "Kategorioversigt", "Link til guide"):
        workbook.create_sheet(name)
    sheet["A5"] = "EXAMPLE"
    sheet["A6"] = "EXAMPLE"
    for row in range(5, 14):
        sheet[f"D{row}"] = f"=LEN(C{row})"
        sheet[f"F{row}"] = f"=LEN(E{row})"
        sheet[f"H{row}"] = f"=LEN(G{row})"
    product_lines = workbook["Product line"]
    product_lines.append(["AGr", "Description"])
    product_lines.append(["128", "Clarins spec. products"])
    categories = workbook["Data for drop downs"]
    categories.append(["Item category", "Description", "Combined"])
    categories.append(["740", "MKU face primer", "740 MKU face primer"])
    categories.append(["741", "MKU face powder compact", "741 MKU face powder compact"])
    workbook.save(path)
    return path


def make_product(*, compact: bool = False) -> ApprovedProduct:
    if compact:
        return ApprovedProduct(
            SourceProduct("80133745", "TEST SI CPCT POWDR GDT U0", "3666057505959", "U0 neutral very light", "SI POWDER U0"),
            ProductProposal("12817743184", "12", "128668", "12804", "128", "Clarins"),
        )
    return ApprovedProduct(
        SourceProduct("80133626", "TEST SI INSTANT SMOOTH 15ML", "3666057504815", "Instant Smooth perfecting touch", "INSTANT SMOOTH"),
        ProductProposal("12819220316", "12", "128591", "12804", "128", "Clarins"),
    )


def make_golden(*, compact: bool = False) -> FakeGoldenRecord:
    if compact:
        return FakeGoldenRecord([
            GoldenRecordProduct("128668741U0", "SI CPCT POWDR GDT U0", "U0 neutral very light", "00", "128668", "Skin Illusion Compact Powder", "12804", "Make-up", "128", "Clarins", "741", "MKU face powder compact", "80133745", "SI POWDER U0")
        ])
    return FakeGoldenRecord([
        GoldenRecordProduct("12859174015", "INSTANT SMOOTH 15ML", "Instant Smooth perfecting touch", "12", "128591", "Instant Smooth", "12804", "Make-up", "128", "Clarins", "740", "MKU face primer", "80133626", "INSTANT SMOOTH")
    ])


def make_batch(analysis_id: str, products: list[ApprovedProduct]) -> web.ApprovalBatch:
    return web.ApprovalBatch(
        analysis_id=analysis_id,
        requested_count=len(products),
        approved_count=len(products),
        blocked_count=0,
        approved_products=products,
    )


def _set_template_paths(
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(web, "MASTERDATA_TEMPLATE_PATH", template_path)
    monkeypatch.setattr(
        web,
        "MASTERDATA_REFERENCE_TEMPLATE_PATH",
        template_path,
    )
    web._cached_masterdata_reference.cache_clear()


def test_download_uses_data_driven_masterdata_semantics(
    client: TestClient,
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_id = "analysis-approved"
    web.approved_batches[analysis_id] = make_batch(analysis_id, [make_product()])
    web.golden_record = make_golden()
    _set_template_paths(template_path, monkeypatch)

    response = client.get(f"/analyses/{analysis_id}/masterdata.xlsx")

    assert response.status_code == 200
    sheet = load_workbook(BytesIO(response.content), data_only=False)["Master template"]
    assert sheet["C5"].value == "TEST SI INSTANT SMOOTH 15ML"
    assert sheet["E5"].value == "Instant Smooth perfecting touch"
    assert sheet["G5"].value is None
    assert sheet["J5"].value == "128591"
    assert sheet["K5"].value is None
    assert sheet["L5"].value == "12804"
    assert sheet["M5"].value == "128S"
    assert sheet["N5"].value == "740 MKU face primer"
    assert sheet["A6"].value is None


def test_download_compact_powder_uses_category_not_product_line(
    client: TestClient,
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_id = "analysis-compact"
    web.approved_batches[analysis_id] = make_batch(analysis_id, [make_product(compact=True)])
    web.golden_record = make_golden(compact=True)
    _set_template_paths(template_path, monkeypatch)

    response = client.get(f"/analyses/{analysis_id}/masterdata.xlsx")

    assert response.status_code == 200
    sheet = load_workbook(BytesIO(response.content), data_only=False)["Master template"]
    assert sheet["K5"].value is None
    assert sheet["I5"].value == "12"
    assert sheet["M5"].value == "128S"
    assert sheet["N5"].value == "741 MKU face powder compact"


def test_rejects_missing_or_empty_approved_batch(client: TestClient) -> None:
    response = client.get("/analyses/missing/masterdata.xlsx")
    assert response.status_code == 404

    web.approved_batches["empty"] = web.ApprovalBatch(
        analysis_id="empty",
        requested_count=1,
        approved_count=0,
        blocked_count=1,
        approved_products=[],
    )
    response = client.get("/analyses/empty/masterdata.xlsx")
    assert response.status_code == 409


def test_rejects_non_approved_product(
    client: TestClient,
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = make_product()
    product.status = "PREPARED"
    web.approved_batches["invalid"] = make_batch("invalid", [product])
    web.golden_record = make_golden()
    _set_template_paths(template_path, monkeypatch)
    response = client.get("/analyses/invalid/masterdata.xlsx")
    assert response.status_code == 409
    assert "Only APPROVED products" in response.json()["detail"]


def test_export_rejects_approved_product_without_mmitno(
    client: TestClient,
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = make_product()
    product.proposal.item_number = None
    web.approved_batches["missing-mmitno"] = make_batch(
        "missing-mmitno",
        [product],
    )
    web.golden_record = make_golden()
    _set_template_paths(template_path, monkeypatch)

    response = client.get("/analyses/missing-mmitno/masterdata.xlsx")

    assert response.status_code == 409
    assert "proposal.item_number is required" in response.json()["detail"]


def test_optional_masterdata_fields_do_not_block_approval(
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_id = "optional-fields"
    product = make_product(compact=True)
    product.source_product.m3_description = None
    product.source_product.receipt_text = None
    golden = make_golden(compact=True)
    golden.products[0].mmfuds = ""
    golden.products[0].receipt_text = ""
    analyzed = SimpleNamespace(
        source_product=product.source_product,
        proposal=product.proposal,
        status="READY",
    )
    verification_item = SimpleNamespace(
        product_key=product.source_product.ean,
        product_code=product.source_product.product_code,
        ean=product.source_product.ean,
        product_name=product.source_product.product_name,
        item_number=product.proposal.item_number,
        status="PREPARED",
        incoming_saether_code=None,
        mmstat="10",
        item_type=product.proposal.item_type,
        brand_code=product.proposal.brand_code,
        brand_name=product.proposal.brand_name,
        item_group=product.proposal.item_group,
        item_class=product.proposal.item_class,
        product_line=None,
        errors=[],
        warnings=[],
    )
    web.analysis_sessions[analysis_id] = SimpleNamespace()
    web.verification_batches[analysis_id] = SimpleNamespace(
        analysis_id=analysis_id,
        requested_count=1,
        prepared_count=1,
        blocked_count=0,
        can_continue=True,
        items=[verification_item],
    )
    web.golden_record = golden
    _set_template_paths(template_path, monkeypatch)
    monkeypatch.setattr(
        web,
        "find_analyzed_product",
        lambda analysis, product_key: analyzed,
    )
    monkeypatch.setattr(
        web,
        "approve_product",
        lambda **kwargs: SimpleNamespace(
            source_product=product.source_product,
            proposal=product.proposal,
            status="APPROVED",
            approved_at="2026-11-11T08:00:00Z",
            approval_source="user",
        ),
    )
    monkeypatch.setattr(web, "serialize_analysis", lambda **kwargs: {})

    response = web.approve_analysis(
        analysis_id,
        web.ApproveRequest(confirmed=True),
    )

    assert response["approval"]["approved_count"] == 1
    assert response["approval"]["blocked_count"] == 0
    assert response["approval"]["ready_for_m3"] is True


def _ready_review_item() -> SimpleNamespace:
    product = make_product()
    product.source_product.product_type = "Tester"
    product.source_product.saether_code = None
    product.proposal.mmstat = "10"
    product.proposal.product_line = "128S"
    product.proposal.needs_review = ()
    return SimpleNamespace(
        source_product=product.source_product,
        proposal=product.proposal,
        status="READY",
        message="Klar",
    )


def _install_review_item(
    item: SimpleNamespace,
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    analysis_id: str = "override-test",
) -> None:
    web.analysis_sessions[analysis_id] = SimpleNamespace()
    web.golden_record = make_golden()
    _set_template_paths(template_path, monkeypatch)
    monkeypatch.setattr(
        web,
        "find_analyzed_product",
        lambda analysis, product_key: item,
    )
    monkeypatch.setattr(web, "serialize_analysis", lambda **kwargs: {})


def test_automatic_masterdata_value_requires_explicit_override(
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _ready_review_item()
    _install_review_item(item, template_path, monkeypatch)

    with pytest.raises(web.HTTPException) as error:
        web.review_product(
            "override-test",
            item.source_product.ean,
            web.ReviewRequest(
                masterdata_review=True,
                product_line="128S",
            ),
        )

    assert error.value.status_code == 400
    assert "Overstyr" in error.value.detail


def test_preview_exposes_non_empty_selectable_override_option_payloads(
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _ready_review_item()
    _install_review_item(item, template_path, monkeypatch)

    preview = web.serialize_masterdata_preview(item)

    product_line_options = preview["product_line_options"]
    item_category_options = preview["item_category_options"]
    assert product_line_options
    assert item_category_options
    assert set(product_line_options) == {"128S"}
    assert set(item_category_options) == {
        "740 MKU face primer",
        "741 MKU face powder compact",
    }
    assert all(
        option["label"]
        for option in preview["product_line_option_details"]
    )
    assert all(
        option["label"]
        for option in preview["item_category_option_details"]
    )


def test_ready_preview_without_mmitno_keeps_dynamic_evidence_and_options(
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _ready_review_item()
    item.proposal.item_number = None
    _install_review_item(item, template_path, monkeypatch)

    preview = web.serialize_masterdata_preview(item)

    assert "error" not in preview
    assert preview["item_number"] is None
    assert preview["m3_name"] == "TEST SI INSTANT SMOOTH 15ML"
    assert preview["text_resolution"]["m3_name"]["source"] == (
        "supplier_product_name"
    )
    assert preview["text_resolution"]["receipt_text"] == {
        "value": None,
        "status": "not_applicable",
        "source": "item_type_rule",
        "reason": "Item type 12 is a tester.",
        "required": False,
        "state": "not_applicable",
    }
    assert preview["product_line"] == "128S"
    assert preview["item_category"] == "740 MKU face primer"
    assert preview["evidence_item_numbers"] == ["12859174015"]
    assert preview["product_line_option_details"]
    assert preview["item_category_option_details"]
    assert preview["blocking_fields"] == []
    assert preview["approval_blocking_fields"] == ["item_number"]
    assert preview["pending_generated_fields"] == ["item_number"]
    assert preview["ready_for_verification"] is True
    assert preview["ready_for_approval"] is False


def test_item_category_override_is_template_controlled_and_resettable(
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _ready_review_item()
    _install_review_item(item, template_path, monkeypatch)

    with pytest.raises(web.HTTPException) as error:
        web.review_product(
            "override-test",
            item.source_product.ean,
            web.ReviewRequest(
                masterdata_review=True,
                item_category="test",
                override_fields=["item_category"],
                override_reason="Test",
            ),
        )
    assert "Data for drop downs" in error.value.detail

    response = web.review_product(
        "override-test",
        item.source_product.ean,
        web.ReviewRequest(
            masterdata_review=True,
            item_category="741 MKU face powder compact",
            override_fields=["item_category"],
            override_reason="Dokumenteret af Masterdata",
        ),
    )
    masterdata = response["product"]["masterdata"]
    assert masterdata["item_category"] == "741 MKU face powder compact"
    assert masterdata["automatic_values"]["item_category"] == (
        "740 MKU face primer"
    )
    assert masterdata["override_fields"] == ["item_category"]

    response = web.review_product(
        "override-test",
        item.source_product.ean,
        web.ReviewRequest(
            masterdata_review=True,
            reset_override_fields=["item_category"],
        ),
    )
    masterdata = response["product"]["masterdata"]
    assert masterdata["item_category"] == "740 MKU face primer"
    assert masterdata["override_fields"] == []



def _unknown_brand_review_item() -> SimpleNamespace:
    item = _ready_review_item()
    item.status = "REVIEW"
    item.message = "Brand kunne ikke bestemmes"
    item.family_match = None
    item.proposal.item_number = None
    item.proposal.brand_code = ""
    item.proposal.brand_name = ""
    item.proposal.item_group = ""
    item.proposal.item_class = ""
    item.proposal.product_line = ""
    item.proposal.needs_review = (
        "brand_code",
        "brand_name",
        "item_group",
        "item_class",
        "product_line",
    )
    return item


def test_unknown_brand_review_exposes_blocking_identity_and_documented_brands(
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _unknown_brand_review_item()
    _install_review_item(item, template_path, monkeypatch, "unknown-brand")

    product = web.serialize_review_product(item)
    preview = product["masterdata"]
    brand_options = web.get_classification_registry().brand_options()

    assert {"brand_code", "brand_name"}.issubset(preview["blocking_fields"])
    assert brand_options == [
        {
            "value": "128|Clarins",
            "code": "128",
            "name": "Clarins",
            "label": "128 — Clarins (1 produkter)",
            "count": 1,
        }
    ]
    assert preview["item_group_options"] == []
    assert preview["item_class_options"] == []


def test_arbitrary_mmitgr_and_mmitcl_are_rejected(
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _unknown_brand_review_item()
    item.proposal.brand_code = "128"
    item.proposal.brand_name = "Clarins"
    _install_review_item(item, template_path, monkeypatch, "invalid-classification")

    with pytest.raises(web.HTTPException) as error:
        web.review_product(
            "invalid-classification",
            item.source_product.ean,
            web.ReviewRequest(item_group="dada", item_class="dad"),
        )

    assert error.value.status_code == 400
    assert "MMITGR" in error.value.detail

    with pytest.raises(web.HTTPException) as error:
        web.review_product(
            "invalid-classification",
            item.source_product.ean,
            web.ReviewRequest(item_group="128591", item_class="dad"),
        )

    assert error.value.status_code == 400
    assert "MMITCL" in error.value.detail


def test_brand_selection_reclassifies_and_promotes_review_to_ready(
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _unknown_brand_review_item()
    _install_review_item(item, template_path, monkeypatch, "brand-promotion")

    response = web.review_product(
        "brand-promotion",
        item.source_product.ean,
        web.ReviewRequest(brand_code="128", brand_name="Clarins"),
    )

    assert response["ready"] is True
    assert response["product"]["status"] == "READY"
    assert response["product"]["brand_code"] == "128"
    assert response["product"]["brand_name"] == "Clarins"
    assert response["product"]["masterdata"]["blocking_fields"] == []
    assert response["product"]["masterdata"]["ready_for_verification"] is True
    assert "flyttet til Klar" in item.message


def test_promoted_product_can_continue_to_verification(
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _unknown_brand_review_item()
    _install_review_item(item, template_path, monkeypatch, "promotion-verify")
    web.review_product(
        "promotion-verify",
        item.source_product.ean,
        web.ReviewRequest(brand_code="128", brand_name="Clarins"),
    )
    # The MVP separates code reservation from final verification.
    item.proposal.item_number = "12899999999"

    def fake_prepare(**kwargs):
        assert item.status == "READY"
        assert kwargs["analysis_id"] == "promotion-verify"
        assert kwargs["products"] == [item]
        return SimpleNamespace(analysis_id="promotion-verify", items=[])

    monkeypatch.setattr(web, "prepare_verification_batch", fake_prepare)
    monkeypatch.setattr(
        web,
        "serialize_verification_batch",
        lambda batch: {"analysis_id": batch.analysis_id, "items": []},
    )

    response = web.prepare_analysis(
        "promotion-verify",
        web.PrepareRequest(product_keys=[item.source_product.ean]),
    )

    assert response["verification"]["analysis_id"] == "promotion-verify"
    assert "promotion-verify" in web.verification_batches



def test_live_analysis_groups_move_promoted_item_to_klar_collection() -> None:
    item = _unknown_brand_review_item()
    analysis = SimpleNamespace(
        review_products=[item],
        ready_products=[],
        existing_products=[],
        ambiguous_products=[],
    )

    item.status = "READY"
    groups = web._current_analysis_groups(analysis)

    assert groups["REVIEW"] == []
    assert groups["READY"] == [item]


def test_code_can_be_reserved_before_complete_masterdata(
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _unknown_brand_review_item()
    item.proposal.brand_code = "128"
    item.proposal.brand_name = "Clarins"
    _install_review_item(item, template_path, monkeypatch, "reserve-before-masterdata")

    monkeypatch.setattr(
        web,
        "serialize_masterdata_preview",
        lambda _item: {
            "blocking_fields": ["item_group", "product_line", "item_category"],
        },
    )

    def fake_prepare(**kwargs):
        assert item.status == "READY"
        assert item.proposal.needs_review == ()
        return SimpleNamespace(
            items=[SimpleNamespace(
                product_key=item.source_product.ean,
                status="PREPARED",
                item_number="12899999999",
                errors=[],
            )]
        )

    monkeypatch.setattr(web, "prepare_verification_batch", fake_prepare)
    monkeypatch.setattr(web, "serialize_analysis", lambda **kwargs: {"ok": True})

    response = web.reserve_codes(
        "reserve-before-masterdata",
        web.ReserveCodeRequest(product_keys=[item.source_product.ean]),
    )

    assert response["reserved_count"] == 1
    assert response["blocked_count"] == 0
    assert item.proposal.item_number == "12899999999"
    assert item.status == "REVIEW"
    assert item.proposal.needs_review != ()
    assert response["reservations"][0]["lifecycle"]["stage"] == "MASTERDATA_REVIEW"


def test_final_verification_requires_reserved_saether_code(
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _ready_review_item()
    item.proposal.item_number = None
    _install_review_item(item, template_path, monkeypatch, "prepare-without-code")

    with pytest.raises(web.HTTPException) as error:
        web.prepare_analysis(
            "prepare-without-code",
            web.PrepareRequest(product_keys=[item.source_product.ean]),
        )

    assert error.value.status_code == 409
    assert "Reservér Sæther Code" in error.value.detail


def test_approval_api_is_tuple_safe(
    template_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = _ready_review_item()
    item.proposal.item_number = "12899999999"
    item.proposal.needs_review = ("item_number", "m3_description")
    analysis_id = "tuple-safe-approval"
    _install_review_item(item, template_path, monkeypatch, analysis_id)
    web.verification_batches[analysis_id] = SimpleNamespace(
        analysis_id=analysis_id,
        items=[SimpleNamespace(
            product_key=item.source_product.ean,
            product_code=item.source_product.product_code,
            ean=item.source_product.ean,
            product_name=item.source_product.product_name,
            item_number=item.proposal.item_number,
            status="PREPARED",
        )],
    )
    monkeypatch.setattr(
        web,
        "get_masterdata_builder",
        lambda **_kwargs: SimpleNamespace(
            build_preview=lambda _item: SimpleNamespace(missing_required_fields=())
        ),
    )
    monkeypatch.setattr(web, "serialize_analysis", lambda **kwargs: {})
    monkeypatch.setattr(web, "serialize_verification_batch", lambda _batch: {})

    response = web.approve_analysis(
        analysis_id,
        web.ApproveRequest(confirmed=True),
    )

    assert response["approval"]["approved_count"] == 0
    assert response["approval"]["blocked_count"] == 1
    assert item.proposal.needs_review == (
        "item_number",
        "m3_description",
    )
