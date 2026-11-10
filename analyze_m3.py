from collections import Counter

from app.golden_record import GoldenRecord


def percentage(count, total):
    if total == 0:
        return 0

    return count / total * 100


def main():
    print("Indlæser Golden Record...")

    golden_record = GoldenRecord().load()
    products = golden_record.products

    total = len(products)

    print(f"\nProdukter i alt: {total:,}")

    # MMSTAT-fordeling
    statuses = Counter(
        product.mmstat or "<TOM>"
        for product in products
    )

    print("\n=== MMSTAT ===")

    for status, count in statuses.most_common():
        print(
            f"{status:10} "
            f"{count:8,} "
            f"({percentage(count, total):6.2f}%)"
        )

    # Datadækning
    fields = {
        "MMITNO": lambda p: p.mmitno,
        "MMITDS": lambda p: p.mmitds,
        "MMITGR": lambda p: p.mmitgr,
        "MMITCL": lambda p: p.mmitcl,
        "MMITTY": lambda p: p.mmity,
        "MMBUAR": lambda p: p.mmbuar,
        "MMBUARTX40": lambda p: p.mmbuartx40,
        "MMCFI1": lambda p: p.mmcfi1,
        "MMCFI1TX40": lambda p: p.mmcfi1tx40,
        "MPPOPN": lambda p: p.ean,
    }

    print("\n=== FELTDÆKNING ===")

    for field_name, getter in fields.items():
        populated = sum(
            1
            for product in products
            if getter(product)
        )

        missing = total - populated

        print(
            f"{field_name:12} "
            f"udfyldt: {populated:8,} "
            f"({percentage(populated, total):6.2f}%) "
            f"mangler: {missing:8,}"
        )


if __name__ == "__main__":
    main()