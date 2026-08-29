from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import router
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="RegBridge API",
        summary="FDA/CDER-scoped legacy eCTD reuse risk-analyzer research prototype.",
        description=(
            "Decision-support contracts for evidence-grounded, version-aware analysis. "
            "RegBridge is not FDA-certified and does not predict submission acceptance."
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.reg_bridge_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Accept"],
    )
    application.include_router(router)
    return application


app = create_app()

