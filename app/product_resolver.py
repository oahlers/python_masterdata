from dataclasses import dataclass

from app.golden_record import GoldenRecord
from app.models import M3Product, SourceProduct


@dataclass
class ProductResolution:
    """
    Resultatet af opslaget af et leverandørprodukt
    mod Golden Record.
    """

    status: str
    source_product: SourceProduct
    existing_products: list[M3Product]
    message: str

    @property
    def is_existing(self) -> bool:
        return self.status == "EXISTING_PRODUCT"

    @property
    def is_new(self) -> bool:
        return self.status == "NEW_PRODUCT"

    @property
    def is_ambiguous(self) -> bool:
        return self.status in {
            "AMBIGUOUS",
            "IDENTIFIER_CONFLICT",
        }


class ProductResolver:
    """
    Afgør om et indkommende produkt allerede findes
    i Golden Record.

    Der bruges kun dokumenterbare identifikatorer:
    - indkommende Sæther Code som MMITNO
    - EAN

    Produktnavnet bruges aldrig som identifikator.
    """

    def __init__(self, golden_record: GoldenRecord):
        self.golden_record = golden_record

    def resolve(
        self,
        source_product: SourceProduct,
    ) -> ProductResolution:
        incoming_item_number = (
            str(source_product.saether_code).strip()
            if source_product.saether_code
            else None
        )
        incoming_ean = (
            str(source_product.ean).strip()
            if source_product.ean
            else None
        )

        item_number_match = None
        if incoming_item_number:
            item_number_match = (
                self.golden_record.find_by_item_number(
                    incoming_item_number
                )
            )

        ean_matches = []
        if incoming_ean:
            ean_matches = self.golden_record.find_by_ean(
                incoming_ean
            )

        if len(ean_matches) > 1:
            matches = list(ean_matches)
            if (
                item_number_match is not None
                and all(
                    product.mmitno != item_number_match.mmitno
                    for product in matches
                )
            ):
                matches.append(item_number_match)

            return ProductResolution(
                status="AMBIGUOUS",
                source_product=source_product,
                existing_products=matches,
                message=(
                    "EAN matcher flere produkter i Golden Record "
                    "og kræver derfor manuel kontrol."
                ),
            )

        ean_match = (
            ean_matches[0]
            if len(ean_matches) == 1
            else None
        )

        if item_number_match is not None:
            if incoming_ean:
                golden_record_ean = item_number_match.ean

                if golden_record_ean != incoming_ean:
                    related = [item_number_match]
                    if (
                        ean_match is not None
                        and ean_match.mmitno
                        != item_number_match.mmitno
                    ):
                        related.append(ean_match)

                    return ProductResolution(
                        status="IDENTIFIER_CONFLICT",
                        source_product=source_product,
                        existing_products=related,
                        message=(
                            f"Indkommende Sæther Code "
                            f"{incoming_item_number} findes allerede "
                            "i Golden Record, men identifikatorerne "
                            "stemmer ikke. "
                            f"Indkommende EAN: {incoming_ean}. "
                            f"Golden Record EAN: "
                            f"{golden_record_ean or 'mangler'}."
                        ),
                    )

            return ProductResolution(
                status="EXISTING_PRODUCT",
                source_product=source_product,
                existing_products=[item_number_match],
                message=(
                    "Indkommende Sæther Code findes allerede "
                    "i Golden Record som MMITNO "
                    f"{item_number_match.mmitno}."
                ),
            )

        if ean_match is not None:
            if incoming_item_number:
                return ProductResolution(
                    status="IDENTIFIER_CONFLICT",
                    source_product=source_product,
                    existing_products=[ean_match],
                    message=(
                        f"EAN {incoming_ean} findes allerede i "
                        "Golden Record som MMITNO "
                        f"{ean_match.mmitno}, men leverandørfilen "
                        "angiver den ikke-eksisterende Sæther Code "
                        f"{incoming_item_number}."
                    ),
                )

            return ProductResolution(
                status="EXISTING_PRODUCT",
                source_product=source_product,
                existing_products=[ean_match],
                message=(
                    "EAN findes allerede i Golden Record "
                    f"som MMITNO {ean_match.mmitno}."
                ),
            )

        if incoming_item_number:
            return ProductResolution(
                status="NEW_PRODUCT",
                source_product=source_product,
                existing_products=[],
                message=(
                    f"Hverken indkommende Sæther Code "
                    f"{incoming_item_number} eller EAN "
                    "findes i Golden Record."
                ),
            )

        if not incoming_ean:
            return ProductResolution(
                status="NEW_PRODUCT",
                source_product=source_product,
                existing_products=[],
                message=(
                    "Produktet har hverken EAN eller en indkommende "
                    "Sæther Code, der kan matches i Golden Record."
                ),
            )

        return ProductResolution(
            status="NEW_PRODUCT",
            source_product=source_product,
            existing_products=[],
            message="EAN findes ikke i Golden Record.",
        )
