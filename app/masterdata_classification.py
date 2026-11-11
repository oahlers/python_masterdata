"""Evidence-based MASTERDATA classification and description derivation.

No brand, family, product-line or item-category mapping is embedded here.  All
classification values come from synchronized M3/Golden Record rows and the
current MASTERDATA template reference sheets.  A value is returned only when
the strongest relevant evidence agrees.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import re
from typing import Any, Callable

from app.masterdata_reference import TemplateReferenceData
from app.masterdata_text import resolve_m3_text


_GENERIC_NAME_TOKENS = {
    "test",
    "tester",
    "sample",
    "new",
    "ny",
    "ml",
    "gr",
    "g",
    "stk",
}
_VARIANT_TOKEN = re.compile(r"^[a-z]{1,3}\d{1,3}$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DocumentedClassification:
    item_type: str | None = None
    item_group: str | None = None
    item_group_description: str | None = None
    item_group_exists: bool = False
    product_group: str | None = None
    product_group_description: str | None = None
    product_line_code: str | None = None
    product_line_description: str | None = None
    item_category_code: str | None = None
    item_category_description: str | None = None
    item_category_combined: str | None = None
    m3_name: str | None = None
    m3_name_status: str | None = None
    m3_name_source: str | None = None
    m3_name_reason: str | None = None
    m3_description: str | None = None
    m3_description_status: str | None = None
    m3_description_source: str | None = None
    m3_description_reason: str | None = None
    receipt_text: str | None = None
    receipt_text_status: str | None = None
    receipt_text_source: str | None = None
    receipt_text_reason: str | None = None
    receipt_text_required: bool = False
    evidence_item_numbers: tuple[str, ...] = ()
    review_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, order=True)
class _EvidenceScore:
    direct: int
    variant: int
    family: int
    item_type: int
    name_overlap: int
    status: int


@dataclass(frozen=True, slots=True)
class _Candidate:
    score: _EvidenceScore
    product: Any


def derive_documented_classification(
    proposal: Any,
    golden_record: Any,
    *,
    source_product: Any | None = None,
    template_reference: TemplateReferenceData | None = None,
) -> DocumentedClassification:
    """Derive one conservative MASTERDATA proposal.

    MMBUAR and MMBUARTX40 are both required for brand identity.  Explicit
    sibling identifiers, exact EAN/reference matches and exact variant evidence
    outrank family matches.  Broad brand-level majorities are never used.
    Equally strong conflicting values remain blank and are surfaced through
    ``review_fields``.
    """

    brand_code = _identifier_or_none(
        _coalesce(
            _read(proposal, "brand_code", "mmbuar"),
            _read(source_product, "brand_code", "mmbuar"),
        )
    )
    brand_name = _text_or_none(
        _coalesce(
            _read(proposal, "brand_name", "mmbuartx40"),
            _read(source_product, "brand_name", "mmbuartx40"),
        )
    )

    review: set[str] = set()
    if brand_code is None or brand_name is None:
        review.update(
            field
            for field, value in (
                ("brand_code", brand_code),
                ("brand_name", brand_name),
            )
            if value is None
        )
        return _with_documented_descriptions(
            proposal,
            source_product,
            (),
            review,
            item_type=_identifier_or_none(
                _read(proposal, "item_type", "mmity")
            ),
        )

    candidates: list[_Candidate] = []
    for product in _products(golden_record):
        if not _same_brand(product, brand_code, brand_name):
            continue
        score = _evidence_score(proposal, source_product, product)
        if score is not None:
            candidates.append(_Candidate(score, product))

    strongest = _strongest_candidates(candidates)
    if not strongest:
        review.update(
            {
                "item_group",
                "product_group",
                "product_line",
                "item_category",
            }
        )
        return _with_documented_descriptions(
            proposal,
            source_product,
            (),
            review,
            item_type=_identifier_or_none(
                _read(proposal, "item_type", "mmity")
            ),
        )

    item_type = _unique(strongest, lambda row: _identifier_or_none(_read(row, "mmity", "mitty")))
    item_group = _unique(strongest, lambda row: _identifier_or_none(_read(row, "mmitgr")))
    item_group_description = _unique(
        strongest,
        lambda row: _text_or_none(_read(row, "mmitgrtx40")),
        normalize=_normalize_text,
    )
    product_group = _unique(
        strongest,
        lambda row: _identifier_or_none(_read(row, "mmitcl")),
    )
    product_group_description = _unique(
        strongest,
        lambda row: _text_or_none(
            _read(row, "mmitcltx40", "product_group_description")
        ),
        normalize=_normalize_text,
    )
    category_code = _unique(
        strongest,
        lambda row: _identifier_or_none(_read(row, "mmcfi1")),
    )
    category_m3_description = _unique(
        strongest,
        lambda row: _text_or_none(_read(row, "mmcfi1tx40")),
        normalize=_normalize_text,
    )

    for field_name, value in (
        ("item_group", item_group),
        ("product_group", product_group),
        ("item_category", category_code),
    ):
        if value is None:
            review.add(field_name)

    product_line_code: str | None = None
    product_line_description: str | None = None
    if template_reference is None:
        review.add("product_line")
    else:
        template_line = template_reference.product_line_for_brand(
            brand_code,
            brand_name,
        )
        if template_line is None:
            review.add("product_line")
        else:
            product_line_code = template_line.export_code
            product_line_description = template_line.description

    category_description: str | None = None
    category_combined: str | None = None
    if category_code is not None and template_reference is not None:
        template_category = template_reference.item_category(category_code)
        if template_category is None:
            review.add("item_category")
        else:
            category_description = template_category.description
            category_combined = template_category.combined
    elif category_code is not None:
        review.add("item_category")

    # MMCFI1TX40 remains useful evidence, but the current template controls the
    # exported description.  A populated M3 description that conflicts with the
    # template is deliberately surfaced for review.
    if (
        category_description is not None
        and category_m3_description is not None
        and not _descriptions_compatible(
            category_description,
            category_m3_description,
        )
    ):
        category_combined = None
        review.add("item_category")

    resolved_item_type = _identifier_or_none(
        _coalesce(
            _read(
                _review_values(proposal, source_product),
                "item_type",
                "mmity",
            ),
            _read(proposal, "item_type", "mmity"),
            item_type,
        )
    )
    documented = _with_documented_descriptions(
        proposal,
        source_product,
        strongest,
        review,
        item_type=resolved_item_type,
    )
    return DocumentedClassification(
        item_type=item_type,
        item_group=item_group,
        item_group_description=item_group_description,
        item_group_exists=item_group is not None,
        product_group=product_group,
        product_group_description=product_group_description,
        product_line_code=product_line_code,
        product_line_description=product_line_description,
        item_category_code=category_code,
        item_category_description=category_description,
        item_category_combined=category_combined,
        m3_name=documented.m3_name,
        m3_name_status=documented.m3_name_status,
        m3_name_source=documented.m3_name_source,
        m3_name_reason=documented.m3_name_reason,
        m3_description=documented.m3_description,
        m3_description_status=documented.m3_description_status,
        m3_description_source=documented.m3_description_source,
        m3_description_reason=documented.m3_description_reason,
        receipt_text=documented.receipt_text,
        receipt_text_status=documented.receipt_text_status,
        receipt_text_source=documented.receipt_text_source,
        receipt_text_reason=documented.receipt_text_reason,
        receipt_text_required=documented.receipt_text_required,
        evidence_item_numbers=tuple(
            value
            for value in (
                _identifier_or_none(_read(row, "mmitno"))
                for row in strongest
            )
            if value is not None
        ),
        review_fields=tuple(sorted(review)),
    )


def _with_documented_descriptions(
    proposal: Any,
    source_product: Any,
    strongest_rows: Iterable[Any],
    review: set[str],
    *,
    item_type: str | None,
) -> DocumentedClassification:
    resolved = resolve_m3_text(
        proposal,
        source_product,
        strongest_rows,
        item_type=item_type,
    )
    review.update(resolved.review_fields)

    return DocumentedClassification(
        m3_name=resolved.m3_name,
        m3_name_status=resolved.m3_name_status,
        m3_name_source=resolved.m3_name_source,
        m3_name_reason=resolved.m3_name_reason,
        m3_description=resolved.m3_description,
        m3_description_status=resolved.m3_description_status,
        m3_description_source=resolved.m3_description_source,
        m3_description_reason=resolved.m3_description_reason,
        receipt_text=resolved.receipt_text,
        receipt_text_status=resolved.receipt_text_status,
        receipt_text_source=resolved.receipt_text_source,
        receipt_text_reason=resolved.receipt_text_reason,
        receipt_text_required=resolved.receipt_text_required,
        review_fields=tuple(sorted(review)),
    )


def _evidence_score(
    proposal: Any,
    source_product: Any,
    product: Any,
) -> _EvidenceScore | None:
    direct = 0
    explicit_sibling = _identifier_or_none(
        _coalesce(
            _read(
                proposal,
                "sibling_item_number",
                "reference_item_number",
                "copy_from_item_number",
            ),
            _read(
                source_product,
                "sibling_item_number",
                "reference_item_number",
                "copy_from_item_number",
            ),
        )
    )
    if explicit_sibling is not None and explicit_sibling == _identifier_or_none(
        _read(product, "mmitno")
    ):
        direct = 4

    source_ean = _identifier_or_none(_read(source_product, "ean", "gtin"))
    product_ean = _identifier_or_none(
        _read(product, "ean", "gtin", "mmean", "mmbarc")
    )
    if source_ean is not None and source_ean == product_ean:
        direct = max(direct, 3)

    source_ref = _identifier_or_none(
        _read(
            source_product,
            "product_code",
            "supplier_item_number",
            "ref_number",
        )
    )
    product_ref = _identifier_or_none(
        _read(
            product,
            "product_code",
            "supplier_item_number",
            "ref_number",
            "mmsuno",
            "mmpopn",
        )
    )
    if source_ref is not None and source_ref == product_ref:
        direct = max(direct, 2)

    source_name = _text_or_none(
        _read(source_product, "product_name", "name", "m3_name")
    )
    product_name = _text_or_none(_read(product, "mmitds", "product_name", "name"))
    source_tokens = _name_tokens(source_name)
    product_tokens = _name_tokens(product_name)
    overlap = len(source_tokens.intersection(product_tokens))
    variant_tokens = {token for token in source_tokens if _VARIANT_TOKEN.match(token)}
    product_variants = {token for token in product_tokens if _VARIANT_TOKEN.match(token)}
    variant = 0
    if variant_tokens and variant_tokens == product_variants and overlap >= 2:
        variant = 2
    elif source_name and product_name and _normalize_text(source_name) == _normalize_text(product_name):
        variant = 3
    elif overlap >= 3:
        variant = 1

    family = 0
    comparisons = (
        ("item_group", "mmitgr", 4),
        ("item_class", "mmitcl", 3),
        ("product_group", "mmitcl", 3),
    )
    seen: set[tuple[str, str]] = set()
    for proposal_name, product_name_field, weight in comparisons:
        key = (proposal_name, product_name_field)
        if key in seen:
            continue
        seen.add(key)
        expected = _identifier_or_none(_read(proposal, proposal_name))
        actual = _identifier_or_none(_read(product, product_name_field))
        if expected is None or actual is None:
            continue
        if expected != actual:
            # A supplied family identifier is a hard boundary.  Product line and
            # category text are not family identifiers and are never compared.
            # MMITTY is deliberately handled below as a ranking bonus: retail,
            # tester, sample and display siblings may share a product family
            # while having different item types.
            return None
        family += weight

    expected_item_type = _identifier_or_none(
        _read(proposal, "item_type", "mmity")
    )
    actual_item_type = _identifier_or_none(
        _read(product, "mmity", "item_type")
    )
    item_type_bonus = int(
        expected_item_type is not None
        and actual_item_type is not None
        and expected_item_type == actual_item_type
    ) * 2

    # Brand-only rows and weak one-token name matches are too broad.
    if direct == 0 and variant == 0 and family < 4:
        return None

    return _EvidenceScore(
        direct=direct,
        variant=variant,
        family=family,
        item_type=item_type_bonus,
        name_overlap=overlap,
        status=_status_preference(_read(product, "mmstat")),
    )


def _strongest_candidates(candidates: Iterable[_Candidate]) -> tuple[Any, ...]:
    candidates = tuple(candidates)
    if not candidates:
        return ()
    strongest_score = max(candidate.score for candidate in candidates)
    return tuple(
        candidate.product
        for candidate in candidates
        if candidate.score == strongest_score
    )


def _same_brand(product: Any, brand_code: str, brand_name: str) -> bool:
    return (
        _normalize_identifier(_read(product, "mmbuar"))
        == _normalize_identifier(brand_code)
        and _normalize_text(_read(product, "mmbuartx40"))
        == _normalize_text(brand_name)
    )


def _unique(
    rows: Iterable[Any],
    getter: Callable[[Any], Any],
    *,
    normalize: Callable[[Any], Any] | None = None,
) -> Any:
    if normalize is None:
        normalize = _normalize_identifier
    values: dict[Any, Any] = {}
    for row in rows:
        value = getter(row)
        if value is None:
            continue
        normalized = normalize(value)
        if normalized is not None:
            values.setdefault(normalized, value)
    if len(values) != 1:
        return None
    return next(iter(values.values()))


def _descriptions_compatible(left: str, right: str) -> bool:
    left_tokens = _name_tokens(left)
    right_tokens = _name_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    return (
        left_tokens == right_tokens
        or left_tokens.issubset(right_tokens)
        or right_tokens.issubset(left_tokens)
    )


def _review_values(proposal: Any, source_product: Any) -> Any:
    return _coalesce(
        _read(proposal, "masterdata_review", "masterdata_overrides"),
        _read(source_product, "masterdata_review", "masterdata_overrides"),
        {},
    )


def _products(golden_record: Any) -> tuple[Any, ...]:
    if golden_record is None:
        return ()
    products = _read(golden_record, "products")
    if products is None:
        products = golden_record
    if isinstance(products, Mapping):
        products = products.values()
    if isinstance(products, (str, bytes)) or not isinstance(products, Iterable):
        return ()
    return tuple(products)


def _read(obj: Any, *names: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Mapping):
        folded = {str(key).casefold(): value for key, value in obj.items()}
        for name in names:
            value = folded.get(name.casefold())
            if value is not None:
                return value
        nested = folded.get("raw_data")
        if isinstance(nested, Mapping) and nested is not obj:
            return _read(nested, *names)
        return None
    for name in names:
        for candidate in (name, name.lower(), name.upper()):
            if hasattr(obj, candidate):
                value = getattr(obj, candidate)
                if value is not None:
                    return value
    nested = getattr(obj, "raw_data", None)
    if isinstance(nested, Mapping):
        return _read(nested, *names)
    return None


def _coalesce(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _identifier_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    result = str(value).strip()
    return result or None


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    result = " ".join(str(value).split())
    return result or None


def _normalize_identifier(value: Any) -> str | None:
    identifier = _identifier_or_none(value)
    return None if identifier is None else identifier.casefold()


def _normalize_text(value: Any) -> str | None:
    text = _text_or_none(value)
    return None if text is None else text.casefold()


def _name_tokens(value: Any) -> set[str]:
    text = _text_or_none(value)
    if text is None:
        return set()
    normalized = re.sub(r"[^a-z0-9]+", " ", text.casefold())
    return {
        token
        for token in normalized.split()
        if token not in _GENERIC_NAME_TOKENS
        and not token.isdigit()
        and len(token) > 1
    }


def _status_preference(value: Any) -> int:
    identifier = _identifier_or_none(value)
    if identifier is None:
        return 0
    try:
        return 1 if int(identifier) <= 50 else -1
    except ValueError:
        return 0
