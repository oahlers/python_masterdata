"""Build MASTERDATA previews and final rows around the SKU lifecycle.

This downstream adapter never calculates or changes an item number.  Analysis
previews may exist before verification reserves MMITNO, while approved/export
rows must already carry that reserved number.  Both paths derive classification
from live Golden Record evidence plus the current template and keep unsupported
values blank for review.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app.masterdata_classification import derive_documented_classification
from app.masterdata_model import MasterDataRecord
from app.masterdata_reference import TemplateReferenceData


DEFAULT_TEMPLATE_PATH = Path("templates/saether_masterdata_template.xlsx")


class MasterDataBuilder:
    def __init__(
        self,
        *,
        golden_record: Any | None = None,
        template_reference: TemplateReferenceData | None = None,
        template_path: str | Path = DEFAULT_TEMPLATE_PATH,
    ) -> None:
        self._golden_record = golden_record
        if template_reference is not None:
            self._template_reference = template_reference
        else:
            path = Path(template_path)
            self._template_reference = (
                TemplateReferenceData.from_xlsx(path)
                if path.is_file()
                else None
            )

    def build(self, approved_product: Any) -> MasterDataRecord:
        _assert_approved(approved_product)
        return self._build(
            approved_product,
            require_item_number=True,
        )

    def build_preview(self, product: Any) -> MasterDataRecord:
        """Build a read-only preview, including before MMITNO reservation."""

        return self._build(
            product,
            require_item_number=False,
        )

    def build_many(
        self,
        approved_products: Iterable[Any],
    ) -> list[MasterDataRecord]:
        return [self.build(product) for product in approved_products]

    def _build(
        self,
        product: Any,
        *,
        require_item_number: bool,
    ) -> MasterDataRecord:
        proposal = _first_present(
            product,
            "proposal",
            "product_proposal",
            default=product,
        )
        source_product = _first_present(
            product,
            "source_product",
            "source",
            default=None,
        )
        if source_product is None:
            source_product = _first_present(
                proposal,
                "source_product",
                "source",
                default=None,
            )
        if source_product is None:
            raise ValueError(
                "Product must expose source_product (directly or via proposal)"
            )

        raw_item_number = _coalesce(
            _read(proposal, "item_number"),
            _read(product, "item_number"),
        )
        item_number = (
            _required_identifier(
                raw_item_number,
                "proposal.item_number",
            )
            if require_item_number
            else _identifier_or_none(raw_item_number)
        )
        review_values = _review_values(proposal, source_product, product)
        documented = derive_documented_classification(
            proposal,
            self._golden_record,
            source_product=source_product,
            template_reference=self._template_reference,
        )

        item_group = _identifier_or_none(
            _coalesce(
                _read(review_values, "item_group"),
                documented.item_group,
            )
        )
        product_group = _identifier_or_none(
            _coalesce(
                _read(review_values, "product_group", "item_class"),
                documented.product_group,
            )
        )
        product_line = _identifier_or_none(
            _coalesce(
                _read(review_values, "product_line"),
                documented.product_line_code,
            )
        )
        item_category = _text_or_none(
            _coalesce(
                _read(review_values, "item_category"),
                documented.item_category_combined,
            )
        )
        item_type = _identifier_or_none(
            _coalesce(
                _read(review_values, "item_type"),
                _read(proposal, "item_type", "mmity"),
                documented.item_type,
            )
        )
        ref_number = _identifier_or_none(
            _read(
                source_product,
                "product_code",
                "supplier_item_number",
                "ref_number",
            )
        )
        ean = _identifier_or_none(_read(source_product, "ean", "gtin"))
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

        explicitly_new_group = _as_bool(
            _read(review_values, "is_new_item_group", "new_item_group")
        )
        new_item_group = explicitly_new_group and not documented.item_group_exists
        item_group_description = None
        if new_item_group:
            item_group_description = _bounded_optional_text(
                _read(
                    review_values,
                    "item_group_description",
                    "new_item_group_description",
                ),
                40,
            )

        review_fields = set(documented.review_fields)
        for field_name, value in (
            ("m3_name", documented.m3_name),
            ("item_type", item_type),
            ("item_group", item_group),
            ("product_group", product_group),
            ("product_line", product_line),
            ("item_category", item_category),
            ("ref_number", ref_number),
            ("ean", ean),
            ("m3_description", documented.m3_description),
            ("receipt_text", documented.receipt_text),
        ):
            if (
                field_name == "receipt_text"
                and documented.receipt_text_status == "not_applicable"
            ):
                review_fields.discard(field_name)
                continue
            if value is None:
                review_fields.add(field_name)
            else:
                review_fields.discard(field_name)
        if new_item_group and item_group_description is None:
            review_fields.add("item_group_description")
        else:
            review_fields.discard("item_group_description")

        return MasterDataRecord(
            item_number=item_number,
            m3_name=documented.m3_name,
            brand_code=brand_code,
            brand_name=brand_name,
            copy_from_item_number=_identifier_or_none(
                _read(review_values, "copy_from_item_number")
            ),
            m3_description=documented.m3_description,
            receipt_text=documented.receipt_text,
            m3_name_status=documented.m3_name_status,
            m3_name_source=documented.m3_name_source,
            m3_name_reason=documented.m3_name_reason,
            m3_description_status=documented.m3_description_status,
            m3_description_source=documented.m3_description_source,
            m3_description_reason=documented.m3_description_reason,
            receipt_text_status=documented.receipt_text_status,
            receipt_text_source=documented.receipt_text_source,
            receipt_text_reason=documented.receipt_text_reason,
            receipt_text_required=documented.receipt_text_required,
            item_type=item_type,
            item_group=item_group,
            item_group_description=item_group_description,
            product_group=product_group,
            product_line=product_line,
            item_category=item_category,
            ref_number=ref_number,
            ean=ean,
            edition=_text_or_none(
                _coalesce(_read(review_values, "edition"), "NY")
            ),
            net_content=_text_or_none(
                _read(source_product, "net_content", "content")
            ),
            content_unit=_text_or_none(
                _read(source_product, "content_unit", "unit")
            ),
            item_group_evidence_description=(
                documented.item_group_description
            ),
            product_group_description=(
                documented.product_group_description
            ),
            product_line_description=(
                documented.product_line_description
            ),
            item_category_code=documented.item_category_code,
            item_category_description=(
                documented.item_category_description
            ),
            evidence_item_numbers=documented.evidence_item_numbers,
            review_fields=tuple(sorted(review_fields)),
        )


def build_masterdata_record(
    approved_product: Any,
    *,
    golden_record: Any | None = None,
    template_reference: TemplateReferenceData | None = None,
    template_path: str | Path = DEFAULT_TEMPLATE_PATH,
) -> MasterDataRecord:
    return MasterDataBuilder(
        golden_record=golden_record,
        template_reference=template_reference,
        template_path=template_path,
    ).build(approved_product)


def _assert_approved(product: Any) -> None:
    for attribute in ("status", "approval_status", "state"):
        if not hasattr(product, attribute):
            continue
        status = getattr(product, attribute)
        if status is None:
            continue
        status = getattr(status, "value", status)
        normalized = str(status).strip().upper()
        if normalized != "APPROVED":
            raise ValueError(
                f"Only APPROVED products can be exported; got {normalized!r}"
            )
        return


def _review_values(*objects: Any) -> Mapping[str, Any]:
    merged: dict[str, Any] = {}
    for obj in objects:
        value = _read(obj, "masterdata_review", "masterdata_overrides")
        if isinstance(value, Mapping):
            merged.update(value)
    return merged


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


def _first_present(obj: Any, *names: str, default: Any) -> Any:
    value = _read(obj, *names)
    return default if value is None else value


def _coalesce(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _identifier_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    result = str(value).strip()
    return result or None


def _required_identifier(value: Any, field_name: str) -> str:
    result = _identifier_or_none(value)
    if result is None:
        raise ValueError(f"{field_name} is required")
    return result


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    result = " ".join(str(value).split())
    return result or None


def _bounded_optional_text(value: Any, limit: int) -> str | None:
    result = _text_or_none(value)
    if result is None:
        return None
    if len(result) > limit:
        raise ValueError(f"reviewed text must not exceed {limit} characters")
    return result


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().casefold() in {"1", "true", "yes", "ja"}
