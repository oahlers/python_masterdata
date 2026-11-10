from collections import Counter
from dataclasses import dataclass

from app.golden_record import GoldenRecord
from app.models import SourceProduct
from app.product_resolver import ProductResolver


@dataclass(frozen=True)
class BrandResolution:
    """
    Resultatet af brandbestemmelse for en importfil.
    """

    status: str

    brand_code: str | None = None
    brand_name: str | None = None

    matched_products: int = 0
    total_products: int = 0

    message: str = ""


def resolve_file_brand(
    source_products: list[SourceProduct],
    golden_record: GoldenRecord,
) -> BrandResolution:
    """
    Forsøger at bestemme brandet for en hel importfil.

    Brand accepteres kun automatisk når alle sikre
    Golden Record-matches peger på præcis samme kombination
    af MMBUAR og MMBUARTX40.

    Der gættes aldrig ud fra:
    - produktnavn
    - MMITNO-prefix
    - filnavn
    - forkortelser som CL
    """

    if not source_products:
        return BrandResolution(
            status="NO_PRODUCTS",
            total_products=0,
            message="Importfilen indeholder ingen produkter.",
        )

    resolver = ProductResolver(golden_record)

    brands = Counter()

    matched_products = 0

    for source_product in source_products:
        result = resolver.resolve(source_product)

        if result.status != "EXISTING_PRODUCT":
            continue

        if len(result.existing_products) != 1:
            continue

        existing_product = result.existing_products[0]

        brand_code = existing_product.mmbuar
        brand_name = existing_product.mmbuartx40

        # Et match uden begge autoritative brandfelter
        # bruges ikke som sikker brandevidens.
        if not brand_code or not brand_name:
            continue

        brands[
            (
                brand_code,
                brand_name,
            )
        ] += 1

        matched_products += 1

    if matched_products == 0:
        return BrandResolution(
            status="NO_EVIDENCE",
            matched_products=0,
            total_products=len(source_products),
            message=(
                "Ingen produkter i importfilen kunne bruges "
                "som sikker brandevidens."
            ),
        )

    if len(brands) != 1:
        brand_summary = ", ".join(
            f"{code} / {name}: {count}"
            for (code, name), count
            in brands.most_common()
        )

        return BrandResolution(
            status="AMBIGUOUS",
            matched_products=matched_products,
            total_products=len(source_products),
            message=(
                "De sikre Golden Record-matches peger på "
                f"flere brands: {brand_summary}"
            ),
        )

    (brand_code, brand_name), count = next(
        iter(brands.items())
    )

    return BrandResolution(
        status="VERIFIED",
        brand_code=brand_code,
        brand_name=brand_name,
        matched_products=count,
        total_products=len(source_products),
        message=(
            f"Alle {count} sikre Golden Record-matches "
            f"peger på {brand_code} / {brand_name}."
        ),
    )