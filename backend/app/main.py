import logging

from fastapi import Depends, FastAPI

from app.api import maintenance, oil, status, tyres, vehicles
from app.api.deps import require_token

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Car Consumable Tracker",
        version="0.1.0",
        description="Track tyres, oil, maintenance and costs of your vehicles.",
    )

    api_deps = [Depends(require_token)]
    for module in (vehicles, tyres, oil, maintenance, status):
        app.include_router(module.router, prefix="/api/v1", dependencies=api_deps)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
