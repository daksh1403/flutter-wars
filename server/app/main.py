"""Application entrypoint.

PLACEHOLDER bootstrap until Module A lands: each feature module contributes
its routers through MODULES, so modules stay independently registerable.
"""

from collections.abc import Sequence

from fastapi import APIRouter, FastAPI

from app.core.errors import install_error_handlers
from app.modules.market import router as market_router
from app.modules.pricing import router as pricing_router

MODULES: dict[str, Sequence[APIRouter]] = {
    "market": (market_router.router, market_router.admin),
    "pricing": (pricing_router.router, pricing_router.admin),
}


def create_app(modules: Sequence[str] | None = None) -> FastAPI:
    app = FastAPI(title="Flutter Wars backend")
    install_error_handlers(app)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for name in MODULES if modules is None else modules:
        for router in MODULES[name]:
            app.include_router(router)
    return app


app = create_app()
