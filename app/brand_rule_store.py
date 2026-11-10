import json
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_STORE_PATH = (
    PROJECT_ROOT
    / "data"
    / "brand_rule_overrides.json"
)


def validate_prefix(
    generation_prefix: str,
) -> str:
    prefix = str(generation_prefix).strip()

    if len(prefix) != 3 or not prefix.isdigit():
        raise ValueError(
            "Generation-prefix skal bestå af præcis tre cifre."
        )

    return prefix


def load_overrides(
    store_path=DEFAULT_STORE_PATH,
) -> dict:
    path = Path(store_path)

    if not path.exists():
        return {}

    with path.open(
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "brand_rule_overrides.json har ugyldigt format."
        )

    return data


def get_override(
    brand_code: str,
    store_path=DEFAULT_STORE_PATH,
) -> dict | None:
    brand_code = str(brand_code).strip()

    overrides = load_overrides(
        store_path
    )

    return overrides.get(
        brand_code
    )


def save_override(
    brand_code: str,
    brand_name: str,
    generation_prefix: str,
    observed_prefixes: set[str] | None = None,
    store_path=DEFAULT_STORE_PATH,
) -> dict:
    brand_code = str(brand_code).strip()
    brand_name = str(brand_name).strip()

    prefix = validate_prefix(
        generation_prefix
    )

    if not brand_code:
        raise ValueError(
            "Brandkode mangler."
        )

    if not brand_name:
        raise ValueError(
            "Brandnavn mangler."
        )

    if observed_prefixes is not None:
        observed = {
            str(value).strip()
            for value in observed_prefixes
        }

        if prefix not in observed:
            raise ValueError(
                f"Prefix {prefix} findes ikke blandt "
                f"de observerede prefixes: "
                f"{sorted(observed)}"
            )

    path = Path(store_path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    overrides = load_overrides(
        path
    )

    existing = overrides.get(
        brand_code
    )

    if existing:
        existing_prefix = existing.get(
            "generation_prefix"
        )

        if existing_prefix != prefix:
            raise ValueError(
                f"Brand {brand_code} har allerede "
                f"generation-prefix {existing_prefix}. "
                "Eksisterende regler overskrives ikke "
                "automatisk."
            )

        return existing

    record = {
        "brand_code": brand_code,
        "brand_name": brand_name,
        "generation_prefix": prefix,
        "source": "user_approved_override",
        "approved_at": (
            datetime.now(timezone.utc).isoformat()
        ),
    }

    overrides[brand_code] = record

    with path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            overrides,
            file,
            indent=2,
            ensure_ascii=False,
        )

    return record