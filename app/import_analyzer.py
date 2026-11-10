from collections import Counter
from dataclasses import dataclass, field

from app.brand_resolver import (
    BrandResolution,
    resolve_file_brand,
)
from app.brand_rules import (
    BrandRuleResolution,
    resolve_brand_rule,
)
from app.family_matcher import (
    FamilyMatchResult,
    match_from_same_sheet,
)
from app.golden_record import GoldenRecord
from app.input_reader import read_excel
from app.models import (
    M3Product,
    ProductProposal,
    SourceProduct,
)
from app.product_builder import (
    build_new_product_proposal,
)
from app.product_resolver import (
    ProductResolution,
    ProductResolver,
)


@dataclass
class AnalyzedProduct:
    source_product: SourceProduct
    status: str

    product_resolution: ProductResolution
    proposal: ProductProposal | None = None
    family_match: FamilyMatchResult | None = None

    existing_products: list[M3Product] = field(
        default_factory=list
    )

    message: str = ""


@dataclass
class ImportAnalysis:
    source_file: str
    total_products: int

    brand_resolution: BrandResolution
    brand_rule_resolution: BrandRuleResolution | None

    products: list[AnalyzedProduct] = field(
        default_factory=list
    )

    @property
    def status_counts(self) -> Counter:
        return Counter(
            product.status
            for product in self.products
        )

    @property
    def existing_products(self) -> list[AnalyzedProduct]:
        return [
            product
            for product in self.products
            if product.status == "EXISTING"
        ]

    @property
    def ready_products(self) -> list[AnalyzedProduct]:
        return [
            product
            for product in self.products
            if product.status == "READY"
        ]

    @property
    def review_products(self) -> list[AnalyzedProduct]:
        return [
            product
            for product in self.products
            if product.status == "REVIEW"
        ]

    @property
    def ambiguous_products(self) -> list[AnalyzedProduct]:
        return [
            product
            for product in self.products
            if product.status in {
                "AMBIGUOUS",
                "IDENTIFIER_CONFLICT",
            }
        ]

    @property
    def identifier_conflicts(self) -> list[AnalyzedProduct]:
        return [
            product
            for product in self.products
            if product.status == "IDENTIFIER_CONFLICT"
        ]


def determine_proposal_status(
    proposal: ProductProposal,
    brand_rule_resolution: BrandRuleResolution | None,
) -> tuple[str, str]:
    """
    Afgør om et nyt produkt er klar til MMITNO-tildeling.

    READY betyder:
    - brandet er verificeret
    - generation-prefixet er verificeret
    - alle obligatoriske klassifikationsfelter er løst
    - kun item_number må mangle

    Der genereres eller reserveres ikke MMITNO i analysestadiet.
    """
    if (
        brand_rule_resolution is None
        or brand_rule_resolution.rule is None
    ):
        status = (
            brand_rule_resolution.status
            if brand_rule_resolution
            else "NOT_FOUND"
        )

        return (
            "REVIEW",
            (
                "Brandets generation-prefix kræver review. "
                f"Status: {status}."
            ),
        )

    blocking_fields = [
        field_name
        for field_name in proposal.needs_review
        if field_name != "item_number"
    ]

    if blocking_fields:
        return (
            "REVIEW",
            (
                "Produktet mangler obligatoriske felter: "
                + ", ".join(blocking_fields)
            ),
        )

    return (
        "READY",
        (
            "Produktet er klassificeret og klar til "
            "MMITNO-tildeling og efterfølgende review."
        ),
    )


def analyze_import(
    path,
    golden_record: GoldenRecord,
) -> ImportAnalysis:
    """
    Analyserer en hel leverandørfil.

    Funktionen:
    - læser Excel
    - sammenholder EAN og incoming Sæther Code med Golden Record
    - blokerer modstridende identifikatorer
    - bestemmer filens brand
    - kontrollerer generation-prefix
    - klassificerer dokumenterbart nye produkter
    - bygger ProductProposal
    - opdeler resultatet i EXISTING, READY, REVIEW,
      AMBIGUOUS og IDENTIFIER_CONFLICT

    Funktionen genererer ikke MMITNO og skriver ikke til M3.
    """
    source_products = read_excel(path)

    source_file = (
        source_products[0].source_file
        if source_products
        else str(path)
    )

    brand_resolution = resolve_file_brand(
        source_products=source_products,
        golden_record=golden_record,
    )

    brand_rule_resolution = None

    if (
        brand_resolution.status == "VERIFIED"
        and brand_resolution.brand_code
    ):
        brand_rule_resolution = resolve_brand_rule(
            brand_code=brand_resolution.brand_code,
            products=golden_record.products,
        )

    analysis = ImportAnalysis(
        source_file=source_file,
        total_products=len(source_products),
        brand_resolution=brand_resolution,
        brand_rule_resolution=brand_rule_resolution,
    )

    resolver = ProductResolver(golden_record)

    for source_product in source_products:
        product_resolution = resolver.resolve(
            source_product
        )

        if product_resolution.status == "EXISTING_PRODUCT":
            analysis.products.append(
                AnalyzedProduct(
                    source_product=source_product,
                    status="EXISTING",
                    product_resolution=product_resolution,
                    existing_products=list(
                        product_resolution.existing_products
                    ),
                    message=product_resolution.message,
                )
            )
            continue

        if product_resolution.status == "IDENTIFIER_CONFLICT":
            analysis.products.append(
                AnalyzedProduct(
                    source_product=source_product,
                    status="IDENTIFIER_CONFLICT",
                    product_resolution=product_resolution,
                    existing_products=list(
                        product_resolution.existing_products
                    ),
                    message=product_resolution.message,
                )
            )
            continue

        if product_resolution.status == "AMBIGUOUS":
            analysis.products.append(
                AnalyzedProduct(
                    source_product=source_product,
                    status="AMBIGUOUS",
                    product_resolution=product_resolution,
                    existing_products=list(
                        product_resolution.existing_products
                    ),
                    message=product_resolution.message,
                )
            )
            continue

        family_match = match_from_same_sheet(
            source_product=source_product,
            all_source_products=source_products,
            resolver=resolver,
        )

        proposal = build_new_product_proposal(
            source_product=source_product,
            brand_resolution=brand_resolution,
            family_match=family_match,
        )

        status, message = determine_proposal_status(
            proposal=proposal,
            brand_rule_resolution=brand_rule_resolution,
        )

        analysis.products.append(
            AnalyzedProduct(
                source_product=source_product,
                status=status,
                product_resolution=product_resolution,
                proposal=proposal,
                family_match=family_match,
                message=message,
            )
        )

    return analysis
