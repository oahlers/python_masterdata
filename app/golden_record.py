import json
from pathlib import Path

from app.models import M3Product


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRODUCTS_PATH = PROJECT_ROOT / "data" / "products.json"


class GoldenRecord:
    """
    Lokal adgang til Golden Record-produkteksporten.

    JSON-filen indlæses én gang ved opstart.
    Derefter foretages opslag via indeks i hukommelsen.
    """

    def __init__(self, products_path=DEFAULT_PRODUCTS_PATH):
        self.products_path = Path(products_path)

        self.products: list[M3Product] = []

        self.by_item_number: dict[str, M3Product] = {}
        self.by_ean: dict[str, list[M3Product]] = {}
        self.by_brand_code: dict[str, list[M3Product]] = {}

    def load(self):
        if not self.products_path.exists():
            raise FileNotFoundError(
                f"Golden Record blev ikke fundet: "
                f"{self.products_path}"
            )

        with self.products_path.open(
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        records = (
            data.get("products", [])
            if isinstance(data, dict)
            else data
        )

        self.products.clear()
        self.by_item_number.clear()
        self.by_ean.clear()
        self.by_brand_code.clear()

        for record in records:
            product = self._to_m3_product(record)

            self.products.append(product)

            if product.mmitno:
                self.by_item_number[product.mmitno] = product

            if product.ean:
                self.by_ean.setdefault(
                    product.ean, []
                ).append(product)

            if product.mmbuar:
                self.by_brand_code.setdefault(
                    product.mmbuar, []
                ).append(product)

        return self

    @staticmethod
    def _clean(value):
        if value is None:
            return None

        value = str(value).strip()

        return value or None

    def _to_m3_product(self, record):
        return M3Product(
            mmitno=self._clean(record.get("MMITNO")),
            mmitds=self._clean(record.get("MMITDS")),

            mmitgr=self._clean(record.get("MMITGR")),
            mmitcl=self._clean(record.get("MMITCL")),
            mmity=self._clean(record.get("MMITTY")),

            mmbuar=self._clean(record.get("MMBUAR")),
            mmbuartx40=self._clean(
                record.get("MMBUARTX40")
            ),

            mmstat=self._clean(record.get("MMSTAT")),

            mmcfi1=self._clean(record.get("MMCFI1")),
            mmcfi1tx40=self._clean(
                record.get("MMCFI1TX40")
            ),

            # I denne Golden Record-eksport ligger
            # EAN/barcode i MPPOPN.
            ean=self._clean(record.get("MPPOPN")),

            raw_data=record,
        )

    def find_by_item_number(self, item_number):
        item_number = self._clean(item_number)

        if not item_number:
            return None

        return self.by_item_number.get(item_number)

    def find_by_ean(self, ean):
        ean = self._clean(ean)

        if not ean:
            return []

        return list(self.by_ean.get(ean, []))

    def find_by_brand_code(self, brand_code):
        brand_code = self._clean(brand_code)

        if not brand_code:
            return []

        return list(
            self.by_brand_code.get(brand_code, [])
        )

    def __len__(self):
        return len(self.products)