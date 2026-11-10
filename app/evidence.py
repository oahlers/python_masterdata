from app.models import M3Product


PRIMARY_REFERENCE_STATUSES = {"20"}


def is_primary_reference(product: M3Product) -> bool:
    """
    Returnerer True når et eksisterende M3-produkt må bruges
    som primær evidens for klassifikation af nye produkter.

    Vi starter konservativt med MMSTAT 20.
    Reglerne udvides kun, når vi har dokumentation for det.
    """

    if product.mmstat not in PRIMARY_REFERENCE_STATUSES:
        return False

    if not product.mmitno:
        return False

    if not product.mmbuar:
        return False

    return True


def primary_reference_products(
    products: list[M3Product],
) -> list[M3Product]:
    """
    Filtrerer en samling M3-produkter til de produkter,
    der må bruges som primær evidens.
    """

    return [
        product
        for product in products
        if is_primary_reference(product)
    ]