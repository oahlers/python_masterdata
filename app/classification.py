import re
from dataclasses import dataclass

from app.models import M3Product, SourceProduct


@dataclass(frozen=True)
class ClassificationResult:
    status: str

    item_group: str | None = None
    item_class: str | None = None

    product_line_code: str | None = None
    product_line_name: str | None = None

    source_items: tuple[str, ...] = ()
    message: str = ""


IGNORED_WORDS = {
    "TEST",
    "TESTER",
    "RET",
    "RETAIL",
    "SMP",
    "SAMPLE",
    "27",
}


def normalize_name(value: str | None) -> list[str]:
    if not value:
        return []

    words = re.findall(
        r"[A-Z0-9]+",
        value.upper(),
    )

    return [
        word
        for word in words
        if word not in IGNORED_WORDS
    ]


def similarity_score(
    source_name: str | None,
    reference_name: str | None,
) -> float:
    source_words = set(
        normalize_name(source_name)
    )

    reference_words = set(
        normalize_name(reference_name)
    )

    if not source_words or not reference_words:
        return 0.0

    shared = source_words & reference_words

    return len(shared) / len(source_words)


def classify_from_references(
    source_product: SourceProduct,
    references: list[M3Product],
    minimum_score: float = 0.60,
) -> ClassificationResult:

    candidates = []

    for reference in references:
        score = similarity_score(
            source_product.product_name,
            reference.mmitds,
        )

        if score >= minimum_score:
            candidates.append(
                (
                    score,
                    reference,
                )
            )

    if not candidates:
        return ClassificationResult(
            status="NO_MATCH",
            message=(
                "Ingen eksisterende referenceprodukter "
                "matcher sikkert nok."
            ),
        )

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    best_score = candidates[0][0]

    best_matches = [
        reference
        for score, reference in candidates
        if score == best_score
    ]

    classifications = {
        (
            product.mmitgr,
            product.mmitcl,
            product.mmcfi1,
            product.mmcfi1tx40,
        )
        for product in best_matches
    }

    # Vi accepterer kun resultatet, hvis alle bedste
    # matches er enige om klassifikationen.
    if len(classifications) != 1:
        return ClassificationResult(
            status="AMBIGUOUS",
            source_items=tuple(
                product.mmitno
                for product in best_matches
                if product.mmitno
            ),
            message=(
                "De bedste referenceprodukter er ikke "
                "enige om klassifikationen."
            ),
        )

    (
        item_group,
        item_class,
        product_line_code,
        product_line_name,
    ) = next(iter(classifications))

    return ClassificationResult(
        status="MATCH",
        item_group=item_group,
        item_class=item_class,
        product_line_code=product_line_code,
        product_line_name=product_line_name,
        source_items=tuple(
            product.mmitno
            for product in best_matches
            if product.mmitno
        ),
        message=(
            f"Entydig klassifikation fra "
            f"{len(best_matches)} bedste referenceprodukt(er) "
            f"med similarity {best_score:.2f}."
        ),
    )