from src.api.routes.conversations import router as conversations_router
from src.api.routes.documents import router as documents_router
from src.api.routes.health import router as health_router
from src.api.routes.ingestion import router as ingestion_router
from src.api.routes.notebooks import router as notebooks_router
from src.api.routes.query import router as query_router
from src.api.routes.studio import router as studio_router

__all__ = [
    "conversations_router",
    "documents_router",
    "health_router",
    "ingestion_router",
    "notebooks_router",
    "query_router",
    "studio_router",
]
