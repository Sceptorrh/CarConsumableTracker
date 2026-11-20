import logging
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import maintenance, oil, status, tyres, vehicles
from app.api.deps import require_token
from app.config import get_settings
from app.web import routes as web

logging.basicConfig(level=logging.INFO)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Car Consumable Tracker",
        version=get_settings().version,
        description="Track tyres, oil, maintenance and costs of your vehicles.",
    )

    api_deps = [Depends(require_token)]
    for module in (vehicles, tyres, oil, maintenance, status):
        app.include_router(module.router, prefix="/api/v1", dependencies=api_deps)

    app.include_router(web.router)
    app.mount("/static", StaticFiles(directory=Path(web.__file__).parent / "static"), name="static")

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
