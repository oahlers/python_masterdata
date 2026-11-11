"""Persistent, concurrency-safe Sæther Code reservations.

The public functions are deliberately small and stable because both the MVP
application and the regression suite use them directly:

``reserve(product, item_number, database_path)``
    Persist one immutable product-to-number assignment.
``get(product, database_path)``
    Reopen the assignment for the same product identity.
``is_reserved(item_number, database_path)``
    Test number availability without changing state.

SQLite uniqueness constraints are the source of truth.  ``BEGIN IMMEDIATE``
serializes competing writers so two concurrent products cannot both win the
same number.  Repeating the exact same assignment is idempotent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Mapping


DEFAULT_DATABASE_PATH = Path("data/item_number_reservations.sqlite3")


class ReservationConflict(ValueError):
    """Raised when a product or item number already has another assignment."""


@dataclass(frozen=True, slots=True)
class ItemNumberReservation:
    product_key: str
    item_number: str
    ean: str | None = None
    product_code: str | None = None
    created_at: str | None = None


# Backwards-compatible name used by a few earlier callers.
Reservation = ItemNumberReservation


def reserve(
    product: Any,
    item_number: Any,
    database_path: str | Path | None = None,
) -> ItemNumberReservation:
    """Persist and return an immutable reservation.

    The same product/number pair may be submitted repeatedly.  A product may
    not receive a second number, and a number may not belong to a second
    product.
    """

    identity = _product_identity(product)
    normalized_number = _identifier(item_number)
    if normalized_number is None:
        raise ValueError("Sæther Code må ikke være tom.")

    path = _database_path(database_path)
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    with _connect(path) as connection:
        _ensure_schema(connection)
        connection.execute("BEGIN IMMEDIATE")
        try:
            by_product = _select_by_product_key(connection, identity.product_key)
            if by_product is not None:
                if by_product.item_number == normalized_number:
                    connection.commit()
                    return by_product
                raise ReservationConflict(
                    "Produktet har allerede en anden persistent reserveret "
                    f"Sæther Code: {by_product.item_number}."
                )

            by_number = _select_by_item_number(connection, normalized_number)
            if by_number is not None:
                if by_number.product_key == identity.product_key:
                    connection.commit()
                    return by_number
                raise ReservationConflict(
                    f"Sæther Code {normalized_number} er allerede persistent "
                    "reserveret til et andet produkt."
                )

            connection.execute(
                """
                INSERT INTO item_number_reservations
                    (product_key, item_number, ean, product_code, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    identity.product_key,
                    normalized_number,
                    identity.ean,
                    identity.product_code,
                    created_at,
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            # A concurrent writer may have committed between the reads and the
            # insert.  Convert SQLite's implementation detail into the stable
            # domain exception expected by callers.
            existing = _read_after_conflict(path, identity.product_key, normalized_number)
            if existing is not None and (
                existing.product_key == identity.product_key
                and existing.item_number == normalized_number
            ):
                return existing
            raise ReservationConflict(
                f"Sæther Code {normalized_number} kunne ikke reserveres entydigt."
            ) from exc
        except Exception:
            connection.rollback()
            raise

    reservation = get(product, path)
    if reservation is None:  # Defensive: a committed row must be observable.
        raise RuntimeError("Reservationen blev ikke gemt.")
    return reservation


def get(
    product: Any,
    database_path: str | Path | None = None,
) -> ItemNumberReservation | None:
    """Return the persistent reservation for ``product``, if any."""

    identity = _product_identity(product)
    path = _database_path(database_path)
    with _connect(path) as connection:
        _ensure_schema(connection)
        return _select_by_product_key(connection, identity.product_key)


def get_by_item_number(
    item_number: Any,
    database_path: str | Path | None = None,
) -> ItemNumberReservation | None:
    """Return the reservation that owns ``item_number``, if any."""

    normalized_number = _identifier(item_number)
    if normalized_number is None:
        return None
    path = _database_path(database_path)
    with _connect(path) as connection:
        _ensure_schema(connection)
        return _select_by_item_number(connection, normalized_number)


def is_reserved(
    item_number: Any,
    database_path: str | Path | None = None,
) -> bool:
    """Return whether ``item_number`` already has a persistent owner."""

    return get_by_item_number(item_number, database_path) is not None


# Compatibility wrappers for older production call sites.
def reserve_item_number(
    product: Any,
    item_number: Any,
    database_path: str | Path | None = None,
) -> ItemNumberReservation:
    return reserve(product, item_number, database_path)


def get_reservation(
    product: Any,
    database_path: str | Path | None = None,
) -> ItemNumberReservation | None:
    return get(product, database_path)


def is_item_number_reserved(
    item_number: Any,
    database_path: str | Path | None = None,
) -> bool:
    return is_reserved(item_number, database_path)


class ItemNumberReservationStore:
    """Object-oriented facade retained for existing application code."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = _database_path(database_path)

    def reserve(self, product: Any, item_number: Any) -> ItemNumberReservation:
        return reserve(product, item_number, self.database_path)

    def get(self, product: Any) -> ItemNumberReservation | None:
        return get(product, self.database_path)

    def get_by_item_number(self, item_number: Any) -> ItemNumberReservation | None:
        return get_by_item_number(item_number, self.database_path)

    def is_reserved(self, item_number: Any) -> bool:
        return is_reserved(item_number, self.database_path)


ReservationStore = ItemNumberReservationStore


@dataclass(frozen=True, slots=True)
class _ProductIdentity:
    product_key: str
    ean: str | None
    product_code: str | None


def _product_identity(product: Any) -> _ProductIdentity:
    if product is None:
        raise ValueError("Produktet mangler ved reservation.")

    ean = _identifier(_read(product, "ean", "gtin", "barcode"))
    product_code = _identifier(
        _read(product, "product_code", "supplier_product_code", "reference", "ref")
    )

    # EAN is the strongest identity available for a new SKU.  Product code is
    # the deterministic fallback for source rows without an EAN.
    if ean is not None:
        key = f"ean:{ean}"
    elif product_code is not None:
        key = f"product_code:{product_code.casefold()}"
    else:
        raise ValueError("Produktet mangler både EAN og produktkode.")

    return _ProductIdentity(product_key=key, ean=ean, product_code=product_code)


def _database_path(database_path: str | Path | None) -> Path:
    path = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=30.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS item_number_reservations (
            product_key TEXT PRIMARY KEY,
            item_number TEXT NOT NULL UNIQUE,
            ean TEXT,
            product_code TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_item_number_reservations_number "
        "ON item_number_reservations(item_number)"
    )


def _select_by_product_key(
    connection: sqlite3.Connection,
    product_key: str,
) -> ItemNumberReservation | None:
    row = connection.execute(
        """
        SELECT product_key, item_number, ean, product_code, created_at
        FROM item_number_reservations
        WHERE product_key = ?
        """,
        (product_key,),
    ).fetchone()
    return _reservation_from_row(row)


def _select_by_item_number(
    connection: sqlite3.Connection,
    item_number: str,
) -> ItemNumberReservation | None:
    row = connection.execute(
        """
        SELECT product_key, item_number, ean, product_code, created_at
        FROM item_number_reservations
        WHERE item_number = ?
        """,
        (item_number,),
    ).fetchone()
    return _reservation_from_row(row)


def _read_after_conflict(
    path: Path,
    product_key: str,
    item_number: str,
) -> ItemNumberReservation | None:
    with _connect(path) as connection:
        _ensure_schema(connection)
        return (
            _select_by_product_key(connection, product_key)
            or _select_by_item_number(connection, item_number)
        )


def _reservation_from_row(row: sqlite3.Row | None) -> ItemNumberReservation | None:
    if row is None:
        return None
    return ItemNumberReservation(
        product_key=row["product_key"],
        item_number=row["item_number"],
        ean=row["ean"],
        product_code=row["product_code"],
        created_at=row["created_at"],
    )


def _read(obj: Any, *names: str) -> Any:
    if isinstance(obj, Mapping):
        folded = {str(key).casefold(): value for key, value in obj.items()}
        for name in names:
            if name.casefold() in folded:
                return folded[name.casefold()]
        return None
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _identifier(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text or None
