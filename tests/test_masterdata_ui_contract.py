from __future__ import annotations

from app.masterdata_ui import summarize_masterdata_review


def test_review_summary_uses_rebuilt_values_and_clear_next_step() -> None:
    summary = summarize_masterdata_review(
        {
            "m3_name": "TEST SI CPCT POWDR GDT U0 5.8G",
            "m3_description": None,
            "receipt_text": None,
            "text_resolution": {
                "receipt_text": {
                    "status": "not_applicable",
                    "reason": "Item type 12 is a tester.",
                }
            },
            "item_type": "12",
            "item_group": "128668",
            "product_group": "12804",
            "product_line": "128S",
            "item_category": "741 MKU face powder compact",
            "evidence": {
                "item_numbers": ["12866874000"],
                "item_group_description": "Skin Illusion Compact Powder",
            },
            "blocking_fields": [],
            "warning_fields": ["m3_description"],
        },
        changed_fields=["m3_name"],
    )

    assert summary["saved_fields"] == ["m3_name"]
    assert summary["values"]["product_line"] == "128S"
    assert summary["values"]["item_category"] == (
        "741 MKU face powder compact"
    )
    assert summary["evidence"]["item_numbers"] == ["12866874000"]
    assert summary["blocking_fields"] == []
    assert summary["warning_fields"] == ["m3_description"]
    assert summary["text_resolution"]["receipt_text"]["status"] == (
        "not_applicable"
    )
    assert summary["ready_for_verification"] is True
    assert summary["next_step"] == (
        "Vælg produktet og fortsæt til verificering."
    )


def test_review_summary_keeps_required_blockers_separate_from_warnings() -> None:
    summary = summarize_masterdata_review(
        {
            "m3_name": "TEST PRODUCT",
            "blocking_fields": ["product_line"],
            "warning_fields": ["m3_description", "receipt_text"],
            "evidence_item_numbers": ["12866874000"],
        },
        changed_fields=[],
    )

    assert summary["ready_for_verification"] is False
    assert summary["blocking_fields"] == ["product_line"]
    assert summary["warning_fields"] == [
        "m3_description",
        "receipt_text",
    ]
    assert summary["evidence"]["item_numbers"] == ["12866874000"]
    assert summary["next_step"] == (
        "Udfyld de krævede felter før verificering."
    )


def test_react_ui_exposes_the_gated_download_and_saved_summary() -> None:
    from pathlib import Path

    source = Path("frontend/src/App.jsx").read_text(encoding="utf-8")

    assert '<WorkflowProgress stage="analysis" />' in source
    assert "Download låses op efter godkendelse" in source
    assert "Download MASTERDATA.xlsx" in source
    assert "setSavedSummary(data.review_summary" in source
    assert "Gemt · preview er genberegnet" in source
    assert "Valgfrit og ikke-blokerende" in source
    assert "Vis afledte MASTERDATA-værdier og evidens" in source
    assert "Ikke relevant for varetype 12" in source
    assert "Ingen dokumenteret værdi fundet" in source
    assert "Kilde: {source}" in source


def test_react_ui_is_review_first_with_explicit_controlled_overrides() -> None:
    from pathlib import Path

    source = Path("frontend/src/App.jsx").read_text(encoding="utf-8")

    assert "Automatisk klassificeret" in source
    assert "Klar til SKU" in source
    assert "Genereres ved verificering" in source
    assert "Overstyr automatisk mapping" not in source
    assert "Udfyld manglende oplysninger" in source
    assert "Ret foreslåede værdier" in source
    assert "Nulstil override" in source
    assert "Begrundelse for override" in source
    assert "Vælg fra Data for drop downs" in source
    assert "item_category_options" in source
    assert "masterdata.item_category_option_details || masterdata.item_category_options" in source
    assert "masterdata.product_line_option_details || masterdata.product_line_options" in source
    assert "function OverrideSelectField" in source
    assert "Aktivér override af ${label}" in source
    assert "selectableOptions.map((option)" in source
    assert "<option key={option.value} value={option.value}>" in source
    assert "disabled={!isSelected('product_line')}" not in source
    assert "disabled={!isSelected('item_category')}" not in source
    assert "masterdata_review: true" in source
    assert "receiptNotApplicable" in source
    assert "receiptAwaitingItemType" in source
    assert "Afventer varetype" in source
    assert "Udfyld dokumenterede tekstmangler" in source


def test_review_ui_is_brand_first_and_never_uses_free_text_for_m3_codes() -> None:
    from pathlib import Path

    source = Path("frontend/src/App.jsx").read_text(encoding="utf-8")

    assert "1. Identificér brand" in source
    assert "Vælg brand og genklassificér" in source
    assert 'type="search"' in source
    assert 'label="MMITGR"' in source
    assert 'label="MMITCL"' in source
    assert 'label="Product Line"' in source
    assert '<ReviewInput label="MMITGR"' not in source
    assert '<ReviewInput label="MMITCL"' not in source
    assert '<ReviewInput label="Product Line"' not in source
    assert "function FamilyCandidates" in source
    assert "setActiveAnalysisTab('ready')" in source
    assert "setSelectedKeys((current)" in source



def test_analysis_results_use_one_compact_active_category_tab() -> None:
    from pathlib import Path

    source = Path("frontend/src/App.jsx").read_text(encoding="utf-8")

    assert "function AnalysisTabs" in source
    assert 'role="tablist"' in source
    assert 'role="tabpanel"' in source
    assert "aria-selected={active}" in source
    assert "{tab.label} ({tab.count})" in source
    assert "label: 'Klar'" in source
    assert "label: 'Kræver review'" in source
    assert "label: 'Kræver afklaring'" in source
    assert "activeAnalysisTab === 'ready'" in source
    assert "activeAnalysisTab === 'review'" in source
    assert "activeAnalysisTab === 'conflict'" in source
    assert "onSelectAll={selectAllReady}" in source
    assert "onClear={() => setSelectedKeys([])}" in source
    assert "conflictAnalysisTabStyle" in source


def test_react_ui_exposes_coherent_mvp_lifecycle_and_reservation_action() -> None:
    from pathlib import Path

    source = Path("frontend/src/App.jsx").read_text(encoding="utf-8")

    assert "Analyse → Kodeklar/review → Sæther Code reserveret" in source
    assert "MASTERDATA-review → Klar til godkendelse → Godkendt → Download" in source
    assert "/reserve-codes" in source
    assert "Bekræft ny vare og reservér Sæther Code" in source
    assert "Reservér Sæther Code" in source
    assert "Næste trin: {lifecycle.next_action}" in source
    assert "product.lifecycle?.can_reserve_code" in source


def test_react_ui_uses_compact_family_bundle_not_mass_m3_lists() -> None:
    from pathlib import Path

    source = Path("frontend/src/App.jsx").read_text(encoding="utf-8")

    assert "candidates.slice(0, 3)" in source
    assert "Kun top 3 vises i hovedflowet" in source
    assert "MMITGR/MMITCL kan ikke kombineres vilkårligt" in source
    assert "Vælges via familie" in source
    assert "Afledes fra brand + template" in source
    assert '<ReviewInput label="MMITGR"' not in source
    assert '<ReviewInput label="MMITCL"' not in source
    assert "candidate.confidence" in source
    assert "candidate.reasons" in source
