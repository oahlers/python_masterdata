from __future__ import annotations

from dataclasses import dataclass

from app.masterdata_registry import GoldenRecordOptionRegistry


@dataclass
class Product:
    mmitno: str
    mmitds: str
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
    ean: str


@dataclass
class Golden:
    products: list[Product]


def _golden() -> Golden:
    return Golden(
        [
            Product(
                "13510010001",
                "LE MALE ELIXIR EDP 75ML",
                "00",
                "135100",
                "Le Male fragrance",
                "13501",
                "Fragrance men",
                "135",
                "Jean Paul Gaultier",
                "100",
                "FRG Eau de parfum",
                "JPG-100",
                "8435415000001",
            ),
            Product(
                "13510010002",
                "TEST LE MALE ELIXIR EDP 75ML",
                "12",
                "135100",
                "Le Male fragrance",
                "13501",
                "Fragrance men",
                "135",
                "Jean Paul Gaultier",
                "100",
                "FRG Eau de parfum",
                "JPG-100-T",
                "8435415000002",
            ),
            Product(
                "13520010001",
                "SCANDAL ABSOLU PARFUM 80ML",
                "00",
                "135200",
                "Scandal fragrance",
                "13502",
                "Fragrance women",
                "135",
                "Jean Paul Gaultier",
                "100",
                "FRG Eau de parfum",
                "JPG-200",
                "8435415000003",
            ),
            Product(
                "34810074001",
                "SOFT LIT FOUNDATION 100 30ML",
                "00",
                "348100",
                "Soft Lit foundation",
                "34804",
                "Make-up",
                "348",
                "Fenty Beauty",
                "740",
                "MKU foundation",
                "FNT-100",
                "8400266000001",
            ),
        ]
    )


def test_brand_options_are_all_observed_pairs_with_counts() -> None:
    options = GoldenRecordOptionRegistry(_golden()).brand_options()

    assert [(item["code"], item["name"], item["count"]) for item in options] == [
        ("348", "Fenty Beauty", 1),
        ("135", "Jean Paul Gaultier", 3),
    ]
    assert all("—" in str(item["label"]) for item in options)


def test_classification_options_are_brand_filtered_and_documented() -> None:
    registry = GoldenRecordOptionRegistry(_golden())
    payload = registry.classification_options(
        brand_code="135",
        brand_name="Jean Paul Gaultier",
        source_product={
            "product_name": "TEST LE MALE ELIXIR EDP 75ML",
            "product_code": "JPG-100-T",
            "ean": "8435415000002",
        },
        proposal={"item_type": "12"},
    )

    assert payload["item_group_options"][0]["value"] == "135100"
    assert payload["item_group_options"][0]["description"] == "Le Male fragrance"
    assert payload["item_group_options"][0]["count"] == 2
    assert payload["item_group_options"][0]["evidence_item_numbers"]
    assert {item["value"] for item in payload["item_group_options"]} == {
        "135100",
        "135200",
    }
    assert all(not str(item["value"]).startswith("348") for item in payload["item_group_options"])


def test_item_class_options_can_be_narrowed_by_selected_family() -> None:
    payload = GoldenRecordOptionRegistry(_golden()).classification_options(
        brand_code="135",
        brand_name="Jean Paul Gaultier",
        selected_item_group="135200",
    )

    assert [item["value"] for item in payload["item_class_options"]] == ["13502"]
    assert payload["family_candidates"][0]["count"] >= 1


def test_unknown_brand_has_no_raw_classification_options() -> None:
    payload = GoldenRecordOptionRegistry(_golden()).classification_options(
        brand_code="999",
        brand_name="Made Up",
    )

    assert payload["selected_brand"] is None
    assert payload["item_group_options"] == []
    assert payload["item_class_options"] == []
    assert payload["family_candidates"] == []


def test_family_payload_is_compact_ranked_and_evidence_backed() -> None:
    golden = _golden()
    for index in range(3, 7):
        golden.products.append(
            Product(
                f"135{index}0010001",
                f"OTHER FAMILY {index}",
                "00",
                f"135{index}00",
                f"Family {index}",
                f"1350{index}",
                "Fragrance",
                "135",
                "Jean Paul Gaultier",
                "100",
                "FRG Eau de parfum",
                f"JPG-{index}00",
                f"84354150000{index}",
            )
        )

    payload = GoldenRecordOptionRegistry(golden).classification_options(
        brand_code="135",
        brand_name="Jean Paul Gaultier",
        source_product={"product_name": "LE MALE ELIXIR EDP 75ML"},
        proposal={"item_type": "00"},
    )

    assert len(payload["family_candidates"]) == 3
    assert payload["family_candidate_count"] > 3
    assert payload["has_more_family_candidates"] is True
    assert all(0 <= item["confidence"] <= 100 for item in payload["family_candidates"])
    assert all(item["reasons"] for item in payload["family_candidates"])
    assert payload["item_type_options"]
