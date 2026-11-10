import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.models import SourceProduct


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DATABASE_PATH = (
    PROJECT_ROOT
    / "data"
    / "reservations.db"
)


@dataclass(frozen=True)
class ItemNumberReservation:
    item_number: str
    product_key: str
    product_code: str | None
    ean: str | None
    created_at: str


def get_product_key(
    product: SourceProduct,
) -> str:
    """
    Stabil identifikation af et indkommende produkt.

    EAN foretrækkes, fordi det er stærkeste identifikator.
    Product code bruges kun hvis EAN mangler.
    """

    if product.ean:
        return f"ean:{product.ean}"

    if product.product_code:
        return f"product_code:{product.product_code}"

    raise ValueError(
        "Produktet mangler både EAN og product code."
    )


def connect(
    database_path=DEFAULT_DATABASE_PATH,
) -> sqlite3.Connection:
    path = Path(database_path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        path
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS item_number_reservations (
            item_number TEXT PRIMARY KEY,
            product_key TEXT NOT NULL UNIQUE,
            product_code TEXT,
            ean TEXT,
            created_at TEXT NOT NULL
        )
        """
    )

    connection.commit()

    return connection


def row_to_reservation(
    row: sqlite3.Row,
) -> ItemNumberReservation:
    return ItemNumberReservation(
        item_number=row["item_number"],
        product_key=row["product_key"],
        product_code=row["product_code"],
        ean=row["ean"],
        created_at=row["created_at"],
    )


def get_reservation_for_product(
    product: SourceProduct,
    database_path=DEFAULT_DATABASE_PATH,
) -> ItemNumberReservation | None:
    product_key = get_product_key(
        product
    )

    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT
                item_number,
                product_key,
                product_code,
                ean,
                created_at
            FROM item_number_reservations
            WHERE product_key = ?
            """,
            (product_key,),
        ).fetchone()

    if row is None:
        return None

    return row_to_reservation(
        row
    )


def item_number_is_reserved(
    item_number: str,
    database_path=DEFAULT_DATABASE_PATH,
) -> bool:
    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM item_number_reservations
            WHERE item_number = ?
            """,
            (str(item_number),),
        ).fetchone()

    return row is not None


def reserve_item_number(
    product: SourceProduct,
    item_number: str,
    database_path=DEFAULT_DATABASE_PATH,
) -> ItemNumberReservation:
    """
    Reserverer MMITNO permanent for produktet.

    Samme produkt får altid samme reservation.

    Samme MMITNO kan aldrig reserveres til to produkter.
    """

    item_number = str(
        item_number
    ).strip()

    if not item_number:
        raise ValueError(
            "MMITNO må ikke være tomt."
        )

    product_key = get_product_key(
        product
    )

    existing = get_reservation_for_product(
        product=product,
        database_path=database_path,
    )

    if existing is not None:
        if existing.item_number != item_number:
            raise ValueError(
                f"Produktet har allerede reserveret "
                f"MMITNO {existing.item_number}."
            )

        return existing

    created_at = (
        datetime.now(timezone.utc).isoformat()
    )

    try:
        with connect(database_path) as connection:
            connection.execute(
                """
                INSERT INTO item_number_reservations (
                    item_number,
                    product_key,
                    product_code,
                    ean,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item_number,
                    product_key,
                    product.product_code,
                    product.ean,
                    created_at,
                ),
            )

            connection.commit()

    except sqlite3.IntegrityError as error:
        raise ValueError(
            f"MMITNO {item_number} er allerede reserveret."
        ) from error

    return ItemNumberReservation(
        item_number=item_number,
        product_key=product_key,
        product_code=product.product_code,
        ean=product.ean,
        created_at=created_at,
    )