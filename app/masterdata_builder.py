"""Build MASTERDATA records from products already approved by the SKU flow.

The builder is a downstream consumer.  It does not calculate or change an item
number and therefore does not modify the frozen SKU creation engine.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.masterdata_model import MasterDataRecord


# Only mappings confirmed by the Golden Record/template investigation are
# included.  Add new entries only when an authoritative source confirms them.
VERIFIED_ITEM_GROUP_DESCRIPTIONS: Mapping[str, str] = {
    "128591": "Instant Smooth",
}

VERIFIED_PRODUCT_LINE_CODES: Mapping[str, str] = {
    "mku face primer": "740",
}


class MasterDataBuilder:
    """Map ``ApprovedProduct`` instances to :class:`MasterDataRecord`.

    The project has used both nested and flattened representations while the
    workflow evolved.  This class prefers ``approved_product.proposal`` and
    ``approved_product.source_product`` but accepts equivalent attributes on
    the approved object itself.  That compatibility is intentionally confined
    to this downstream adapter.
    """

    def __init__(
        self,
        *,
        item_group_descriptions: Mapping[str, str] | None = None,
        product_line_codes: Mapping[str, str] | None = None,
    ) -> None:
        self._item_group_descriptions = dict(
            item_group_descriptions or VERIFIED_ITEM_GROUP_DESCRIPTIONS
        )
        self._product_line_codes = {
            str(key).strip().casefold(): _identifier(value)
            for key, value in (
                product_line_codes or VERIFIED_PRODUCT_LINE_CODES
            ).items()
        }

    def build(self, approved_product: Any) -> MasterDataRecord:
        """Build a documented export record for one approved product.

        A present status field must be ``APPROVED``.  ``ApprovedProduct``
        classes without an explicit status are accepted because their type
        already represents that invariant.
        """

        _assert_approved(approved_product)

        proposal = _first_present(
            approved_product,
            "proposal",
            "product_proposal",
            default=approved_product,
        )
        source_product = _first_present(
            approved_product,
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
                "ApprovedProduct must expose source_product (directly or via proposal)"
            )

        item_number = _required_identifier(
            _coalesce(
                _first_present(proposal, "item_number", default=None),
                _first_present(approved_product, "item_number", default=None),
            ),
            "proposal.item_number",
        )
        product_name = _required_text(
            _first_present(source_product, "product_name", "name", default=None),
            "source_product.product_name",
        )
        m3_name = _bounded_text(product_name, 30, uppercase=True)

        item_group = _identifier_or_none(
            _coalesce(
                _first_present(proposal, "item_group", "mmitgr", default=None),
                _first_present(approved_product, "item_group", default=None),
            )
        )
        product_line_value = _coalesce(
            _first_present(
                proposal,
                "product_line_description",
                "product_line",
                "mmcfi1tx40",
                default=None,
            ),
            _first_present(
                approved_product,
                "product_line_description",
                "product_line",
                default=None,
            ),
        )

        item_group_description = _text_or_none(
            _coalesce(
                _first_present(
                    proposal,
                    "item_group_description",
                    "mmitgrtx40",
                    default=None,
                ),
                _first_present(
                    approved_product,
                    "item_group_description",
                    default=None,
                ),
            )
        )
        if item_group_description is None and item_group is not None:
            item_group_description = self._item_group_descriptions.get(item_group)

        product_line_code = _identifier_or_none(
            _coalesce(
                _first_present(
                    proposal,
                    "product_line_code",
                    "mmcfi1",
                    default=None,
                ),
                _first_present(
                    approved_product,
                    "product_line_code",
                    default=None,
                ),
            )
        )
        if product_line_code is None and product_line_value is not None:
            candidate = _identifier_or_none(product_line_value)
            if candidate is not None and candidate.isdigit():
                product_line_code = candidate
            else:
                product_line_code = self._product_line_codes.get(
                    str(product_line_value).strip().casefold()
                )

        return MasterDataRecord(
            item_number=item_number,
            m3_name=m3_name,
            # Undocumented values intentionally stay None.
            copy_from_item_number=None,
            m3_description=None,
            receipt_text=None,
            item_type=_identifier_or_none(
                _coalesce(
                    _first_present(
                        proposal, "item_type", "mmity", default=None
                    ),
                    _first_present(
                        approved_product, "item_type", default=None
                    ),
                )
            ),
            item_group=item_group,
            item_group_description=_bounded_optional_text(
                item_group_description, 40
            ),
            product_group=_identifier_or_none(
                _coalesce(
                    _first_present(
                        proposal,
                        "item_class",
                        "product_group",
                        "mmitcl",
                        default=None,
                    ),
                    _first_present(
                        approved_product,
                        "item_class",
                        "product_group",
                        default=None,
                    ),
                )
            ),
            product_line=product_line_code,
            item_category=None,
            ref_number=_identifier_or_none(
                _first_present(
                    source_product,
                    "product_code",
                    "supplier_item_number",
                    "ref_number",
                    default=None,
                )
            ),
            ean=_identifier_or_none(
                _first_present(source_product, "ean", "gtin", default=None)
            ),
            edition="NY",
        )

    def build_many(
        self, approved_products: Iterable[Any]
    ) -> list[MasterDataRecord]:
        return [self.build(product) for product in approved_products]


def build_masterdata_record(approved_product: Any) -> MasterDataRecord:
    """Convenience wrapper using the verified default mappings."""

    return MasterDataBuilder().build(approved_product)


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


def _first_present(
    obj: Any, *names: str, default: Any
) -> Any:
    if obj is None:
        return default
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return default


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _identifier(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _identifier_or_none(value: Any) -> str | None:
    if value is None:
        return None
    result = _identifier(value)
    return result or None


def _required_identifier(value: Any, field_name: str) -> str:
    result = _identifier_or_none(value)
    if result is None:
        raise ValueError(f"{field_name} is required")
    return result


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _required_text(value: Any, field_name: str) -> str:
    result = _text_or_none(value)
    if result is None:
        raise ValueError(f"{field_name} is required")
    return result


def _bounded_text(value: Any, limit: int, *, uppercase: bool = False) -> str:
    result = _required_text(value, "text")
    if uppercase:
        result = result.upper()
    return result[:limit]


def _bounded_optional_text(value: Any, limit: int) -> str | None:
    result = _text_or_none(value)
    return None if result is None else result[:limit]
