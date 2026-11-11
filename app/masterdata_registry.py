"""Documented review choices derived from the live Golden Record.

The review UI must never invent M3 classification codes.  This module builds a
read-only registry from observed MMBUAR/MMBUARTX40, MMITGR/MMITGRTX40 and
MMITCL/MMITCLTX40 values.  Product-specific payloads are filtered by the exact
selected brand pair and ranked by identifier, item-type and name evidence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from typing import Any


_GENERIC_TOKENS = {
    "test",
    "tester",
    "sample",
    "new",
    "ny",
    "ml",
    "cl",
    "g",
    "gr",
    "stk",
    "pcs",
}
_TOKEN_RE = re.compile(r"[0-9a-zæøå]+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class _ObservedRow:
    product: Any
    brand_code: str
    brand_name: str
    item_number: str | None
    ean: str | None
    supplier_reference: str | None
    item_type: str | None
    item_group: str | None
    item_group_description: str | None
    item_class: str | None
    item_class_description: str | None
    item_category_code: str | None
    item_category_description: str | None
    product_name: str | None


class GoldenRecordOptionRegistry:
    """Indexed, deterministic option payloads for review and API validation."""

    def __init__(self, golden_record: Any) -> None:
        self._rows_by_brand: dict[tuple[str, str], list[_ObservedRow]] = defaultdict(list)
        for product in _products(golden_record):
            code = _identifier(_read(product, "mmbuar", "brand_code"))
            name = _text(_read(product, "mmbuartx40", "brand_name"))
            if code is None or name is None:
                continue
            row = _ObservedRow(
                product=product,
                brand_code=code,
                brand_name=name,
                item_number=_identifier(_read(product, "mmitno", "item_number")),
                ean=_identifier(_read(product, "ean", "gtin")),
                supplier_reference=_identifier(
                    _read(
                        product,
                        "supplier_item_number",
                        "supplier_reference",
                        "ref_number",
                        "product_code",
                    )
                ),
                item_type=_identifier(_read(product, "mmity", "item_type")),
                item_group=_identifier(_read(product, "mmitgr", "item_group")),
                item_group_description=_text(
                    _read(product, "mmitgrtx40", "item_group_description")
                ),
                item_class=_identifier(
                    _read(product, "mmitcl", "item_class", "product_group")
                ),
                item_class_description=_text(
                    _read(
                        product,
                        "mmitcltx40",
                        "item_class_description",
                        "product_group_description",
                    )
                ),
                item_category_code=_identifier(
                    _read(product, "mmcfi1", "item_category_code")
                ),
                item_category_description=_text(
                    _read(product, "mmcfi1tx40", "item_category_description")
                ),
                product_name=_text(_read(product, "mmitds", "product_name", "name")),
            )
            self._rows_by_brand[(code, _normalize_text(name))].append(row)

    def brand_options(self) -> list[dict[str, object]]:
        options = []
        for (code, _normalized_name), rows in self._rows_by_brand.items():
            names = Counter(row.brand_name for row in rows)
            name = sorted(names.items(), key=lambda item: (-item[1], item[0].casefold()))[0][0]
            options.append(
                {
                    "value": f"{code}|{name}",
                    "code": code,
                    "name": name,
                    "label": f"{code} — {name} ({len(rows):,} produkter)",
                    "count": len(rows),
                }
            )
        return sorted(
            options,
            key=lambda option: (
                str(option["name"]).casefold(),
                str(option["code"]),
            ),
        )

    def has_brand(self, brand_code: object, brand_name: object) -> bool:
        return self._brand_key(brand_code, brand_name) in self._rows_by_brand

    def classification_options(
        self,
        *,
        brand_code: object,
        brand_name: object,
        source_product: Any | None = None,
        proposal: Any | None = None,
        selected_item_group: object | None = None,
    ) -> dict[str, object]:
        key = self._brand_key(brand_code, brand_name)
        rows = list(self._rows_by_brand.get(key, ()))
        if not rows:
            return _empty_classification_payload()

        source_name = _text(
            _coalesce(
                _read(source_product, "product_name", "name"),
                _read(proposal, "product_name", "name"),
            )
        )
        source_ean = _identifier(
            _coalesce(
                _read(source_product, "ean", "gtin"),
                _read(proposal, "ean", "gtin"),
            )
        )
        source_reference = _identifier(
            _coalesce(
                _read(
                    source_product,
                    "product_code",
                    "supplier_item_number",
                    "ref_number",
                ),
                _read(
                    proposal,
                    "product_code",
                    "supplier_item_number",
                    "ref_number",
                ),
            )
        )
        source_item_type = _identifier(
            _coalesce(
                _read(proposal, "item_type", "mmity"),
                _read(source_product, "item_type", "mmity"),
            )
        )
        requested_group = _identifier(
            _coalesce(selected_item_group, _read(proposal, "item_group", "mmitgr"))
        )

        scored = [
            (
                _relevance_score(
                    row,
                    source_name=source_name,
                    source_ean=source_ean,
                    source_reference=source_reference,
                    source_item_type=source_item_type,
                ),
                row,
            )
            for row in rows
        ]

        all_family_candidates = _family_payload(scored)
        family_candidates = all_family_candidates[:3]
        item_group_options = _field_payload(
            scored,
            value_getter=lambda row: row.item_group,
            description_getter=lambda row: row.item_group_description,
        )

        class_rows = scored
        if requested_group is not None:
            filtered = [pair for pair in scored if pair[1].item_group == requested_group]
            if filtered:
                class_rows = filtered
        item_class_options = _field_payload(
            class_rows,
            value_getter=lambda row: row.item_class,
            description_getter=lambda row: row.item_class_description,
        )
        item_type_options = _field_payload(
            scored,
            value_getter=lambda row: row.item_type,
            description_getter=lambda _row: None,
        )

        top_confidence = (
            int(family_candidates[0]["confidence"])
            if family_candidates
            else 0
        )
        runner_up_confidence = (
            int(family_candidates[1]["confidence"])
            if len(family_candidates) > 1
            else 0
        )
        auto_family = (
            family_candidates[0]
            if top_confidence >= 90
            and top_confidence - runner_up_confidence >= 15
            else None
        )

        return {
            "selected_brand": {
                "code": rows[0].brand_code,
                "name": rows[0].brand_name,
            },
            "item_group_options": item_group_options,
            "item_class_options": item_class_options,
            "item_type_options": item_type_options,
            "family_candidates": family_candidates,
            "family_candidate_count": len(all_family_candidates),
            "has_more_family_candidates": len(all_family_candidates) > 3,
            "auto_family": auto_family,
            "ambiguous": len(family_candidates) > 1 and (
                not family_candidates
                or top_confidence - runner_up_confidence < 15
            ),
        }

    @staticmethod
    def _brand_key(brand_code: object, brand_name: object) -> tuple[str, str] | None:
        code = _identifier(brand_code)
        name = _text(brand_name)
        if code is None or name is None:
            return None
        return code, _normalize_text(name)


def _field_payload(scored_rows, *, value_getter, description_getter) -> list[dict[str, object]]:
    grouped: dict[str, list[tuple[int, _ObservedRow]]] = defaultdict(list)
    for score, row in scored_rows:
        value = value_getter(row)
        if value is not None:
            grouped[value].append((score, row))

    options: list[dict[str, object]] = []
    for value, pairs in grouped.items():
        descriptions = Counter(
            description_getter(row)
            for _, row in pairs
            if description_getter(row) is not None
        )
        description = None
        if descriptions:
            description = sorted(
                descriptions.items(),
                key=lambda item: (-item[1], item[0].casefold()),
            )[0][0]
        evidence = _evidence_numbers(pairs)
        score = max(score for score, _ in pairs)
        confidence = _confidence(score)
        reasons = _evidence_reasons(pairs)
        label_parts = [value]
        if description:
            label_parts.append(description)
        label = " — ".join(label_parts) + f" · {len(pairs)} produkter"
        if evidence:
            label += f" · fx {', '.join(evidence[:3])}"
        options.append(
            {
                "value": value,
                "code": value,
                "description": description,
                "label": label,
                "count": len(pairs),
                "score": score,
                "evidence_item_numbers": evidence,
            }
        )
    return sorted(
        options,
        key=lambda option: (
            -int(option["score"]),
            -int(option["count"]),
            str(option["code"]),
        ),
    )


def _family_payload(scored_rows) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[tuple[int, _ObservedRow]]] = defaultdict(list)
    for score, row in scored_rows:
        if row.item_group is None or row.item_class is None:
            continue
        grouped[(row.item_group, row.item_class)].append((score, row))

    payload: list[dict[str, object]] = []
    for (item_group, item_class), pairs in grouped.items():
        group_description = _most_common_text(
            row.item_group_description for _, row in pairs
        )
        class_description = _most_common_text(
            row.item_class_description for _, row in pairs
        )
        category_code = _most_common_identifier(
            row.item_category_code for _, row in pairs
        )
        category_description = _most_common_text(
            row.item_category_description for _, row in pairs
        )
        score = max(score for score, _ in pairs)
        confidence = _confidence(score)
        reasons = _evidence_reasons(pairs)
        payload.append(
            {
                "value": f"{item_group}|{item_class}",
                "item_group": item_group,
                "item_group_description": group_description,
                "item_class": item_class,
                "item_class_description": class_description,
                "item_category_code": category_code,
                "item_category_description": category_description,
                "label": (
                    f"{item_group} — {group_description or 'uden beskrivelse'} / "
                    f"{item_class} — {class_description or 'uden beskrivelse'}"
                ),
                "count": len(pairs),
                "score": score,
                "confidence": confidence,
                "reasons": reasons,
                "evidence_item_numbers": _evidence_numbers(pairs),
            }
        )
    return sorted(
        payload,
        key=lambda item: (
            -int(item["score"]),
            -int(item["count"]),
            str(item["item_group"]),
            str(item["item_class"]),
        ),
    )


def _confidence(score: int) -> int:
    if score >= 1000:
        return 100
    if score >= 900:
        return 98
    if score <= 0:
        return 10
    return min(95, 35 + score)


def _evidence_reasons(
    pairs: Iterable[tuple[int, _ObservedRow]],
) -> list[str]:
    score = max((value for value, _row in pairs), default=0)
    reasons: list[str] = []
    if score >= 1000:
        reasons.append("Eksakt EAN-match")
    elif score >= 900:
        reasons.append("Eksakt leverandørreference")
    if any(value >= 40 for value, _row in pairs):
        reasons.append("Varetype/navn matcher")
    reasons.append(f"{len(list(pairs))} Golden Record-reference(r)")
    return reasons


def _relevance_score(
    row: _ObservedRow,
    *,
    source_name: str | None,
    source_ean: str | None,
    source_reference: str | None,
    source_item_type: str | None,
) -> int:
    score = 0
    if source_ean is not None and row.ean == source_ean:
        score += 1000
    if source_reference is not None and row.supplier_reference == source_reference:
        score += 900
    if source_item_type is not None and row.item_type == source_item_type:
        score += 40
    source_tokens = _tokens(source_name)
    row_tokens = _tokens(row.product_name)
    if source_tokens and row_tokens:
        overlap = source_tokens.intersection(row_tokens)
        score += 20 * len(overlap)
        if overlap == source_tokens or overlap == row_tokens:
            score += 30
    return score


def _evidence_numbers(pairs: Iterable[tuple[int, _ObservedRow]]) -> list[str]:
    return list(
        dict.fromkeys(
            row.item_number
            for _score, row in sorted(pairs, key=lambda pair: -pair[0])
            if row.item_number is not None
        )
    )[:10]


def _most_common_text(values: Iterable[str | None]) -> str | None:
    counts = Counter(value for value in values if value is not None)
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))[0][0]


def _most_common_identifier(values: Iterable[str | None]) -> str | None:
    counts = Counter(value for value in values if value is not None)
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _empty_classification_payload() -> dict[str, object]:
    return {
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


def _products(golden_record: Any) -> tuple[Any, ...]:
    if golden_record is None:
        return ()
    for attribute in ("products", "records", "items"):
        value = getattr(golden_record, attribute, None)
        if value is not None and not callable(value):
            return tuple(value)
    if isinstance(golden_record, Mapping):
        return tuple(golden_record.values())
    try:
        return tuple(golden_record)
    except TypeError:
        return ()


def _read(obj: Any, *names: str) -> Any:
    if obj is None:
        return None
    for name in names:
        if isinstance(obj, Mapping):
            for candidate in (name, name.lower(), name.upper()):
                if candidate in obj and obj[candidate] not in (None, ""):
                    return obj[candidate]
        else:
            for candidate in (name, name.lower(), name.upper()):
                if hasattr(obj, candidate):
                    value = getattr(obj, candidate)
                    if value not in (None, ""):
                        return value
    return None


def _coalesce(*values: Any) -> Any:
    return next((value for value in values if value not in (None, "")), None)


def _identifier(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _tokens(value: str | None) -> set[str]:
    if value is None:
        return set()
    return {
        token.casefold()
        for token in _TOKEN_RE.findall(value)
        if token.casefold() not in _GENERIC_TOKENS and not token.isdigit()
    }
