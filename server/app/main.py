"""Thin composition example for Foundation; no engine, JWT code, or fake adapters."""

from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.auction.router import build_router as auction_router
from app.integration.auth import Principal
from app.integration.errors import BusinessError, ConfigurationRequired
from app.integration.runtime import BackendModules
from app.trading.router import build_router as trading_router


def create_app(
    *,
    runtime: BackendModules | None = None,
    principal_dependency: Callable[..., Principal] | None = None,
) -> FastAPI:
    app = FastAPI(title="Flutter Workshop — Trading and Auctions", version="0.1.0")

    def get_runtime() -> BackendModules:
        if runtime is None:
            raise ConfigurationRequired()
        return runtime

    def unconfigured_auth() -> Principal:
        raise HTTPException(status_code=401, detail="Authentication required.")

    auth = principal_dependency or unconfigured_auth

    def require_team(principal: Principal = Depends(auth)) -> UUID:
        if principal.team_id is None:
            raise HTTPException(status_code=403, detail="Participant team required.")
        return principal.team_id

    def require_organizer(principal: Principal = Depends(auth)) -> None:
        if not principal.organizer:
            raise HTTPException(status_code=403, detail="Organizer permission required.")

    @app.exception_handler(BusinessError)
    async def business_error(request: Request, exc: BusinessError):
        # Class-owned public text only: never echo adapter/SQL exception arguments.
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "The operation could not be completed.",
                }
            },
        )

    app.include_router(trading_router(get_runtime, require_team))
    app.include_router(auction_router(get_runtime, require_team, require_organizer))

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
