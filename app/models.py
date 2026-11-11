from dataclasses import dataclass, field
from typing import Any


@dataclass
class SourceProduct:
    """
    Et nyt produkt modtaget fra en leverandør.

    Manglende værdier forbliver None.
    Programmet må ikke gætte manglende information.
    """

    # Leverandørens identifikation
    product_code: str | None = None
    ean: str | None = None
    product_name: str | None = None
    brand_name: str | None = None

    # Eventuelle eksisterende Sæther/BMS-oplysninger
    saether_code: str | None = None
    product_type: str | None = None

    # Hvor produktet kom fra
    source_file: str | None = None

    # Bevarer alle originale leverandørdata,
    # også felter vi endnu ikke har modelleret.
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class M3Product:
    """Et eksisterende produkt fra Golden Record / M3."""

    mmitno: str | None = None
    mmitds: str | None = None
    mmitgr: str | None = None
    mmitcl: str | None = None
    mmity: str | None = None

    mmbuar: str | None = None
    mmbuartx40: str | None = None

    mmstat: str | None = None

    mmcfi1: str | None = None
    mmcfi1tx40: str | None = None

    ean: str | None = None

    # Bevarer den originale Golden Record-data.
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Evidence:
    """Forklarer hvorfor programmet foreslår en bestemt værdi."""

    field_name: str
    proposed_value: str
    source: str

    source_item_numbers: list[str] = field(default_factory=list)
    details: str | None = None


@dataclass
class ProductProposal:
    """
    Det produkt programmet foreslår at oprette.

    None betyder, at der ikke er tilstrækkelig evidens til at udfylde feltet.
    """

    source_product: SourceProduct

    item_number: str | None = None

    brand_code: str | None = None
    brand_name: str | None = None

    # Et verificeret generation-prefix fra brand_rules. Det er ikke MMBUAR.
    generation_prefix: str | None = None

    item_group: str | None = None
    item_class: str | None = None
    item_type: str | None = None

    product_line: str | None = None

    # Nye produkter skal oprettes som MMSTAT 10.
    mmstat: str = "10"

    # Evidens gemmes pr. foreslået felt.
    evidence: dict[str, Evidence] = field(default_factory=dict)

    # Felter som ikke kunne bestemmes sikkert.
    needs_review: list[str] = field(default_factory=list)
