import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    # Datakilde
    data_source: str = os.getenv(
        "DATA_SOURCE",
        "local",
    )

    # Lokal Golden Record fallback
    local_products_path: str = os.getenv(
        "LOCAL_PRODUCTS_PATH",
        "data/products.json",
    )

    # Azure Cosmos DB
    cosmos_endpoint: str | None = os.getenv(
        "COSMOS_ENDPOINT"
    )

    cosmos_database: str | None = os.getenv(
        "COSMOS_DATABASE"
    )

    cosmos_container: str | None = os.getenv(
        "COSMOS_CONTAINER"
    )

    def cosmos_configured(self) -> bool:
        return all(
            [
                self.cosmos_endpoint,
                self.cosmos_database,
                self.cosmos_container,
            ]
        )


settings = Settings()