"""FastAPI application factory.

Run with:  uvicorn app.main:create_app --factory --port 8000
(or ``python run.py``)
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.errors import error_body
from app.api.handlers import ApiHandlers
from app.api.routes import build_router
from app.config import Settings
from app.context import build_context
from app.services.errors import DomainError
from app.services.phone import InvalidPhoneError

log = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    ctx = build_context(settings)  # raises ConfigError in live mode when credentials are missing

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info("Meridian voice assistant API ready in %s mode", settings.app_mode.upper())
        yield
        if ctx.live is not None:
            await ctx.live.close()

    app = FastAPI(
        title="Voice AI Doctor Appointment Assistant",
        version=__version__,
        description="REST API + SSE feed + WebRTC signalling for the voice appointment assistant.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError):
        status, body = error_body(exc)
        return JSONResponse(body, status_code=status)

    @app.exception_handler(InvalidPhoneError)
    async def _phone_error(_: Request, exc: InvalidPhoneError):
        status, body = error_body(exc)
        return JSONResponse(body, status_code=status)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        fields = [".".join(str(p) for p in e["loc"] if p != "body") for e in exc.errors()]
        return JSONResponse(
            {"error": {"code": "validation_error", "message": "Invalid request: " + ", ".join(fields), "fields": fields}},
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        log.exception("Unhandled error")
        status, body = error_body(exc)
        return JSONResponse(body, status_code=status)

    app.include_router(build_router(ApiHandlers(ctx)))

    if settings.is_live:
        from app.voice.live_routes import register_live_routes  # imports pipecat

        register_live_routes(app, ctx)

    dist = Path(settings.frontend_dist)
    if dist.is_dir():  # `npm run build` output: serve the dashboard from the same port
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="dashboard")
    return app
