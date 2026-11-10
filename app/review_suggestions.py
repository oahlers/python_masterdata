from dataclasses import dataclass
from pathlib import Path

from app.classification_feedback_store import (
    DEFAULT_STORE_PATH,
    find_feedback,
)
from app.models import ProductProposal


@dataclass(frozen=True)
class ReviewSuggestion:
    field_name: str
    suggested_value: str

    evidence_count: int
    source: str

    message: str


SUGGESTABLE_FIELDS = {
    "item_type",
    "item_group",
    "item_class",
    "product_line",
}


def get_field_suggestion(
    proposal: ProductProposal,
    field_name: str,
    store_path: str | Path = DEFAULT_STORE_PATH,
) -> ReviewSuggestion | None:
    """
    Finder et forslag fra tidligere bruger-feedback.

    Et forslag returneres kun hvis alle tidligere
    beslutninger i præcis samme kontekst er enige.

    Funktionen ændrer aldrig ProductProposal.
    """

    if field_name not in SUGGESTABLE_FIELDS:
        return None

    matches = find_feedback(
        proposal=proposal,
        field_name=field_name,
        store_path=store_path,
    )

    if not matches:
        return None

    values = {
        record.get("selected_value")
        for record in matches
        if record.get("selected_value")
    }

    if len(values) != 1:
        return None

    suggested_value = next(
        iter(values)
    )

    return ReviewSuggestion(
        field_name=field_name,
        suggested_value=suggested_value,
        evidence_count=len(matches),
        source="user_feedback",
        message=(
            f"{len(matches)} tidligere "
            "brugergodkendt(e) beslutning(er) "
            "i samme kontekst peger på "
            f"{suggested_value}."
        ),
    )


def get_review_suggestions(
    proposal: ProductProposal,
    store_path: str | Path = DEFAULT_STORE_PATH,
) -> list[ReviewSuggestion]:
    """
    Finder forslag til de felter, som produktet
    aktuelt mangler.

    item_number håndteres ikke her.
    """

    suggestions = []

    for field_name in proposal.needs_review:
        if field_name not in SUGGESTABLE_FIELDS:
            continue

        suggestion = get_field_suggestion(
            proposal=proposal,
            field_name=field_name,
            store_path=store_path,
        )

        if suggestion is not None:
            suggestions.append(
                suggestion
            )

    return suggestions