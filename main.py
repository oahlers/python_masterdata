from collections import Counter

from app.golden_record import GoldenRecord
from app.evidence import primary_reference_products


def main():
    print("Indlæser Golden Record...")

    golden_record = GoldenRecord().load()

    print(f"Produkter indlæst: {len(golden_record):,}")

    # Clarins = MMBUAR 128
    clarins = golden_record.find_by_brand_code("128")

    print(f"\nClarins i alt: {len(clarins):,}")

    references = primary_reference_products(clarins)

    print(
        f"Clarins godkendt som primær evidens: "
        f"{len(references):,}"
    )

    statuses = Counter(
        product.mmstat
        for product in references
    )

    print("\nMMSTAT blandt referenceprodukter:")

    for status, count in statuses.items():
        print(f"{status}: {count:,}")

    print("\nEksempler:")

    for product in references[:10]:
        print(
            product.mmitno,
            "|",
            product.mmitds,
            "| GR:",
            product.mmitgr,
            "| CL:",
            product.mmitcl,
            "| CFI1:",
            product.mmcfi1tx40,
        )


if __name__ == "__main__":
    main()