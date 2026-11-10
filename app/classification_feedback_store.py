import json
from datetime import datetime, timezone
from pathlib import Path

from app.models import ProductProposal


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_STORE_PATH = (
    PROJECT_ROOT
    / "data"
    / "classification_feedback.json"
)


def load_feedback(
    store_path=DEFAULT_STORE_PATH,
) -> list[dict]:
    path = Path(store_path)

    if not path.exists():
        return []

    with path.open(
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(
            "classification_feedback.json "
            "har ugyldigt format."
        )

    return data


def build_context(
    proposal: ProductProposal,
) -> dict:
    """
    Bygger den kontekst et bruger-valg blev foretaget i.

    Vi gemmer ikke kun BMS Product Type.
    """

    return {
        "brand_code": proposal.brand_code,
        "brand_name": proposal.brand_name,
        "product_type": (
            proposal.source_product.product_type
        ),
        "item_group": proposal.item_group,
        "item_class": proposal.item_class,
        "product_line": proposal.product_line,
    }


def save_feedback(
    proposal: ProductProposal,
    field_name: str,
    selected_value: str,
    store_path=DEFAULT_STORE_PATH,
) -> dict:
    """
    Gemmer en brugergodkendt klassifikationsbeslutning.

    Funktionen lærer ikke automatisk en global regel.
    Den gemmer beslutningen sammen med dens kontekst.
    """

    selected_value = str(
        selected_value
    ).strip()

    if not selected_value:
        raise ValueError(
            "Den valgte værdi må ikke være tom."
        )

    context = build_context(
        proposal
    )

    record = {
        "field_name": field_name,
        "selected_value": selected_value,
        "context": context,
        "source_product": {
            "product_code": (
                proposal.source_product.product_code
            ),
            "ean": (
                proposal.source_product.ean
            ),
            "product_name": (
                proposal.source_product.product_name
            ),
        },
        "source": "user_review",
        "approved_at": (
            datetime.now(timezone.utc).isoformat()
        ),
    }

    path = Path(store_path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    feedback = load_feedback(
        path
    )

    feedback.append(
        record
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            feedback,
            file,
            indent=2,
            ensure_ascii=False,
        )

    return record


def find_feedback(
    proposal: ProductProposal,
    field_name: str,
    store_path=DEFAULT_STORE_PATH,
) -> list[dict]:
    """
    Finder tidligere brugerbeslutninger med samme kontekst.

    Ingen værdi anvendes automatisk her.
    Funktionen returnerer kun evidensen.
    """

    expected_context = build_context(
        proposal
    )

    feedback = load_feedback(
        store_path
    )

    return [
        record
        for record in feedback
        if (
            record.get("field_name")
            == field_name
            and record.get("context")
            == expected_context
        )
    ]


def get_consistent_feedback_value(
    proposal: ProductProposal,
    field_name: str,
    store_path=DEFAULT_STORE_PATH,
) -> str | None:
    """
    Returnerer en tidligere værdi kun hvis alle fundne
    brugerbeslutninger i præcis samme kontekst er enige.

    Modstridende historik giver None.
    """

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

    return next(iter(values))