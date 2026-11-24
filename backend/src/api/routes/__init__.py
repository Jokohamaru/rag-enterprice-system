from src.api.routes.documents import router as documents_router
from src.api.routes.health import router as health_router
from src.api.routes.ingestion import router as ingestion_router

__all__ = ["documents_router", "health_router", "ingestion_router"]
