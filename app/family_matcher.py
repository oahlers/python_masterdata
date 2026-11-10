import re
from dataclasses import dataclass

from app.models import M3Product, SourceProduct
from app.product_resolver import ProductResolver


@dataclass(frozen=True)
class FamilyMatchResult:
    status: str

    item_group: str | None = None
    item_class: str | None = None

    product_line_code: str | None = None
    product_line_name: str | None = None

    matched_source_code: str | None = None
    matched_item_number: str | None = None

    score: float = 0.0
    message: str = ""


WORD_ALIASES = {
    "CPCT": "COMPACT",
    "POWDR": "POWDER",
    "PWDR": "POWDER",
    "LIQ": "LIQUID",
    "EYESHDW": "EYESHADOW",
    "EYESHADW": "EYESHADOW",
    "LQUID": "LIQUID",
    "CRM": "CREAM",
}


IGNORED_WORDS = {
    "TEST",
    "TESTER",
    "RET",
    "RETAIL",
    "SMP",
    "SAMPLE",
    "SMPCD",
    "GDT",
    "INT",
}


def normalize_family_words(
    value: str | None,
) -> set[str]:
    if not value:
        return set()

    words = re.findall(
        r"[A-Z0-9]+(?:\.[0-9]+)?",
        value.upper(),
    )

    normalized = set()

    for word in words:
        word = WORD_ALIASES.get(word, word)

        if word in IGNORED_WORDS:
            continue

        # Størrelser som 10G, 5.8G, 15ML og 0.5G
        # beskriver ikke nødvendigvis produktfamilien.
        if re.fullmatch(
            r"\d+(?:\.\d+)?(?:ML|G|GR|PCS)",
            word,
        ):
            continue

        # Årstal/prefix som 27 bruges ikke som familieord.
        if word == "27":
            continue

        normalized.add(word)

    return normalized


def family_similarity(
    left: str | None,
    right: str | None,
) -> float:
    left_words = normalize_family_words(left)
    right_words = normalize_family_words(right)

    if not left_words or not right_words:
        return 0.0

    shared = left_words & right_words
    union = left_words | right_words

    return len(shared) / len(union)


def match_from_same_sheet(
    source_product: SourceProduct,
    all_source_products: list[SourceProduct],
    resolver: ProductResolver,
    minimum_score: float = 0.45,
) -> FamilyMatchResult:
    source_sheet = source_product.raw_data.get(
        "_source_sheet"
    )

    if not source_sheet:
        return FamilyMatchResult(
            status="NO_SOURCE_SHEET",
            message="Produktet mangler kildeark.",
        )

    candidates = []

    for candidate in all_source_products:
        if candidate is source_product:
            continue

        candidate_sheet = candidate.raw_data.get(
            "_source_sheet"
        )

        if candidate_sheet != source_sheet:
            continue

        resolution = resolver.resolve(candidate)

        if resolution.status != "EXISTING_PRODUCT":
            continue

        if len(resolution.existing_products) != 1:
            continue

        existing = resolution.existing_products[0]

        # Tester-varianter skal klassificeres ud fra
        # den tilhørende retail-familie, ikke samples.
        if source_product.product_type == "0E":
            if candidate.product_type not in {"0A", "0A4"}:
                continue

        score = family_similarity(
            source_product.product_name,
            candidate.product_name,
        )


        if score < minimum_score:
            continue

        candidates.append(
            (
                score,
                candidate,
                existing,
            )
        )

    if not candidates:
        return FamilyMatchResult(
            status="NO_MATCH",
            message=(
                "Ingen sikker eksisterende familie blev "
                "fundet i samme inputark."
            ),
        )

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    best_score = candidates[0][0]

    best_candidates = [
        item
        for item in candidates
        if item[0] == best_score
    ]

    classifications = {
        (
            existing.mmitgr,
            existing.mmitcl,
            existing.mmcfi1,
            existing.mmcfi1tx40,
        )
        for _, _, existing in best_candidates
    }

    if len(classifications) != 1:
        return FamilyMatchResult(
            status="AMBIGUOUS",
            score=best_score,
            message=(
                "De bedste familiematches er ikke enige "
                "om klassifikationen."
            ),
        )

    _, matched_source, matched_existing = (
        best_candidates[0]
    )

    return FamilyMatchResult(
        status="MATCH",
        item_group=matched_existing.mmitgr,
        item_class=matched_existing.mmitcl,
        product_line_code=matched_existing.mmcfi1,
        product_line_name=matched_existing.mmcfi1tx40,
        matched_source_code=matched_source.product_code,
        matched_item_number=matched_existing.mmitno,
        score=best_score,
        message=(
            "Entydigt familiematch fra samme inputark: "
            f"{matched_source.product_code} / "
            f"{matched_existing.mmitno}."
        ),
    )