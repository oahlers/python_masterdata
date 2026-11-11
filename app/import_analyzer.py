from collections import Counter
from dataclasses import dataclass, field

from app.brand_resolver import BrandResolution, resolve_file_brand
from app.brand_rules import BrandRuleResolution, resolve_brand_rule
from app.family_matcher import FamilyMatchResult, match_from_same_sheet
from app.golden_record import GoldenRecord
from app.input_reader import read_excel
from app.item_number_generator import validate_generation_prefix
from app.models import M3Product, ProductProposal, SourceProduct
from app.product_builder import build_new_product_proposal
from app.product_resolver import (
    AMBIGUOUS,
    EXISTING_PRODUCT,
    IDENTIFIER_CONFLICT,
    NEW_PRODUCT,
    ProductResolution,
    ProductResolver,
)


IDENTITY_TO_WORKFLOW = {
    EXISTING_PRODUCT: "EXISTING",
    IDENTIFIER_CONFLICT: "IDENTIFIER_CONFLICT",
    AMBIGUOUS: "AMBIGUOUS",
}


@dataclass
class AnalyzedProduct:
    source_product: SourceProduct
    status: str
    product_resolution: ProductResolution
    proposal: ProductProposal | None = None
    family_match: FamilyMatchResult | None = None
    existing_products: list[M3Product] = field(default_factory=list)
    message: str = ""


@dataclass
class ImportAnalysis:
    source_file: str
    total_products: int
    brand_resolution: BrandResolution
    brand_rule_resolution: BrandRuleResolution | None
    products: list[AnalyzedProduct] = field(default_factory=list)

    @property
    def status_counts(self) -> Counter:
        return Counter(product.status for product in self.products)

    @property
    def existing_products(self) -> list[AnalyzedProduct]:
        return [product for product in self.products if product.status == "EXISTING"]

    @property
    def ready_products(self) -> list[AnalyzedProduct]:
        return [product for product in self.products if product.status == "READY"]

    @property
    def review_products(self) -> list[AnalyzedProduct]:
        return [product for product in self.products if product.status == "REVIEW"]

    @property
    def ambiguous_products(self) -> list[AnalyzedProduct]:
        return [
            product for product in self.products if product.status == "AMBIGUOUS"
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
    """Return READY only for a fully classified proposal with verified prefix."""

    if brand_rule_resolution is None or brand_rule_resolution.rule is None:
        status = (
            brand_rule_resolution.status
            if brand_rule_resolution is not None
            else "NOT_FOUND"
        )
        return (
            "REVIEW",
            f"Brandets generation-prefix kræver review. Status: {status}.",
        )

    try:
        verified_prefix = validate_generation_prefix(
            brand_rule_resolution.rule.generation_prefix
        )
    except ValueError as exc:
        return "REVIEW", str(exc)

    if proposal.generation_prefix != verified_prefix:
        return (
            "REVIEW",
            "ProductProposal mangler brand-reglens verificerede generation-prefix.",
        )

    blocking_fields = [
        field_name
        for field_name in proposal.needs_review
        if field_name != "item_number"
    ]
    if blocking_fields:
        return (
            "REVIEW",
            "Produktet mangler obligatoriske felter: " + ", ".join(blocking_fields),
        )

    return (
        "READY",
        "Produktet er klassificeret og klar til Sæther Code-tildeling.",
    )


def analyze_import(path, golden_record: GoldenRecord) -> ImportAnalysis:
    """Analyze identities and proposals without generating or reserving codes."""

    source_products = read_excel(path)
    source_file = source_products[0].source_file if source_products else str(path)

    brand_resolution = resolve_file_brand(
        source_products=source_products,
        golden_record=golden_record,
    )
    brand_rule_resolution = None
    if brand_resolution.status == "VERIFIED" and brand_resolution.brand_code:
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
        product_resolution = resolver.resolve(source_product)

        if product_resolution.status != NEW_PRODUCT:
            workflow_status = IDENTITY_TO_WORKFLOW.get(product_resolution.status)
            if workflow_status is None:
                raise RuntimeError(
                    "ProductResolver returnerede en status uden workflow-mapping: "
                    f"{product_resolution.status}"
                )
            analysis.products.append(
                AnalyzedProduct(
                    source_product=source_product,
                    status=workflow_status,
                    product_resolution=product_resolution,
                    existing_products=list(product_resolution.existing_products),
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

        if brand_rule_resolution is not None and brand_rule_resolution.rule is not None:
            proposal.generation_prefix = validate_generation_prefix(
                brand_rule_resolution.rule.generation_prefix
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
