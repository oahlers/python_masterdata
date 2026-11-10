from dataclasses import dataclass


@dataclass(frozen=True)
class BmsProductTypeRule:
    code: str
    name: str
    description: str
    m3_item_type: str | None = None
    edition: str | None = None


# Dokumenteret BMS-semantik.
#
# m3_item_type udfyldes kun, hvor vi har en dokumenteret
# BMS -> M3 Item Type mapping.
#
# None betyder bevidst:
# Mappingen er ikke dokumenteret godt nok til automatisk brug.
BMS_PRODUCT_TYPE_RULES = {
    "0A": BmsProductTypeRule(
        code="0A",
        name="Regular sales product",
        description=(
            "Normal salgsvare, bortset fra value packs, "
            "sets og vrac-produkter."
        ),
        m3_item_type="00",
    ),

    "0A2": BmsProductTypeRule(
        code="0A2",
        name="Value pack / coffret / set",
        description="Coffrets, value packs og sets.",
        m3_item_type="41",
    ),

    "0A4": BmsProductTypeRule(
        code="0A4",
        name="Limited edition",
        description=(
            "Limited products, one shots og punctuals."
        ),
        m3_item_type="00",
        edition="OS",
    ),

    "0B": BmsProductTypeRule(
        code="0B",
        name="Salon-size product",
        description="Vrac-produkter dedikeret til SPA.",
    ),

    "0C": BmsProductTypeRule(
        code="0C",
        name="Sample",
        description=(
            "Overordnet BMS-klassifikation for basic "
            "og promotional samples."
        ),
    ),

    "0C1": BmsProductTypeRule(
        code="0C1",
        name="Basic sample / sample card",
        description="Basic samples og sample cards.",
        m3_item_type="22",
    ),

    "0C2": BmsProductTypeRule(
        code="0C2",
        name="Novelty sample",
        description="Novelties samples i tubes.",
        m3_item_type="22",
    ),

    "0C3": BmsProductTypeRule(
        code="0C3",
        name="Punctual sample / sachet",
        description="Punctual samples som sachets.",
        m3_item_type="22",
    ),

    "0D": BmsProductTypeRule(
        code="0D",
        name="Trial coffret",
        description=(
            "Prepacked trial gifts/coffrets."
        ),
    ),

    "0D1": BmsProductTypeRule(
        code="0D1",
        name="Skincare trial",
        description="Skincare trial.",
    ),

    "0D2": BmsProductTypeRule(
        code="0D2",
        name="Skincare discovery",
        description="Skincare discovery size.",
    ),

    "0D3": BmsProductTypeRule(
        code="0D3",
        name="Makeup miniature / trial",
        description="Makeup miniature eller trial.",
        m3_item_type="30",
    ),

    "0E": BmsProductTypeRule(
        code="0E",
        name="Tester",
        description="Testerprodukt.",
        m3_item_type="12",
    ),

    "0F": BmsProductTypeRule(
        code="0F",
        name="Dummy",
        description="Dummy-produkt.",
    ),

    "0G": BmsProductTypeRule(
        code="0G",
        name="Counter merchandiser",
        description="Counter merchandiser / shipper.",
        m3_item_type="33",
    ),

    "0H": BmsProductTypeRule(
        code="0H",
        name="Tester glorifier",
        description="Counter tester / glorifier.",
    ),

    "0I": BmsProductTypeRule(
        code="0I",
        name="General tester unit",
        description="General tester unit / module.",
    ),

    "0I1": BmsProductTypeRule(
        code="0I1",
        name="Permanent tester material",
        description=(
            "Permanent GTU, gondola, drawers "
            "eller tilsvarende materiale."
        ),
    ),

    "0J": BmsProductTypeRule(
        code="0J",
        name="Showcard",
        description="Showcard.",
    ),

    "0L": BmsProductTypeRule(
        code="0L",
        name="Module visual",
        description="Visual/materiale til modul.",
    ),

    "0M": BmsProductTypeRule(
        code="0M",
        name="Uniform material",
        description=(
            "Uniformer, badges og makeup belts."
        ),
    ),

    "0N": BmsProductTypeRule(
        code="0N",
        name="Wrapping material",
        description="Wrapping material.",
    ),

    "0O": BmsProductTypeRule(
        code="0O",
        name="Brochure",
        description="Brochure.",
    ),

    "0P": BmsProductTypeRule(
        code="0P",
        name="Leaflet",
        description="Leaflet.",
    ),

    "0Q": BmsProductTypeRule(
        code="0Q",
        name="Technical material",
        description=(
            "Technical material såsom tester brushes, "
            "POS accessories og SPA-materiale."
        ),
    ),

    "0R": BmsProductTypeRule(
        code="0R",
        name="Training material / accessory",
        description=(
            "Training material og makeup accessories."
        ),
        m3_item_type="33",
    ),

    "0T": BmsProductTypeRule(
        code="0T",
        name="Consumer gift",
        description=(
            "Consumer gifts og tomme pouches."
        ),
    ),

    "0V": BmsProductTypeRule(
        code="0V",
        name="Sales staff gift",
        description=(
            "Sales girls gifts / avant premieres."
        ),
    ),
}


def normalize_product_type(
    product_type: str | None,
) -> str | None:
    if product_type is None:
        return None

    normalized = product_type.strip().upper()

    return normalized or None


def find_product_type_rule(
    product_type: str | None,
) -> BmsProductTypeRule | None:
    normalized = normalize_product_type(product_type)

    if normalized is None:
        return None

    return BMS_PRODUCT_TYPE_RULES.get(normalized)


def get_bms_description(
    product_type: str | None,
) -> str | None:
    rule = find_product_type_rule(product_type)

    if rule is None:
        return None

    return rule.description


def get_m3_item_type(
    product_type: str | None,
) -> str | None:
    """
    Returnerer kun M3 Item Type når mappingen er
    dokumenteret.

    Ukendt eller udokumenteret mapping -> None.
    """

    rule = find_product_type_rule(product_type)

    if rule is None:
        return None

    return rule.m3_item_type


def get_edition(
    product_type: str | None,
) -> str | None:
    """
    0A4 er dokumenteret Limited Edition og giver OS.

    Alle andre typer giver None, indtil Edition kan
    dokumenteres fra input eller en anden autoritativ kilde.
    """

    rule = find_product_type_rule(product_type)

    if rule is None:
        return None

    return rule.edition