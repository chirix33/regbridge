"""Storage backends for analysis records and product TTL stores."""

from app.persistence.factory import (
    ProductStores,
    create_analysis_repository,
    create_product_stores,
)

__all__ = [
    "ProductStores",
    "create_analysis_repository",
    "create_product_stores",
]
