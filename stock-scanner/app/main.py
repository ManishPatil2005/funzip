"""Application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__, db
from app.api.routes import api, public
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import BodySizeLimitMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware

BASE = Path(__file__).parent
log = logging.getLogger("scanner")


def create_app() -> FastAPI:
    settings = get_settings()  # validates production requirements
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        db.init_db()
        log.info("scanner %s started env=%s provider=%s", __version__, settings.env, settings.data_provider)
        if not settings.api_keys:
            log.warning("SCANNER_API_KEYS is empty: authentication is DISABLED (development only)")
        yield

    app = FastAPI(
        title="Market Scanner",
        version=__version__,
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # Middleware order: last added runs first (outermost).
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["X-API-Key", "Content-Type"], allow_credentials=False, max_age=600,
        )
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.hsts)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))

    app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
    templates = Jinja2Templates(directory=BASE / "templates")  # autoescape on by default

    @app.get("/", include_in_schema=False)
    def scanner_page(request: Request):
        return templates.TemplateResponse(request, "scanner.html", {"page": "scanner", "version": __version__})

    @app.get("/builder", include_in_schema=False)
    def builder_page(request: Request):
        return templates.TemplateResponse(request, "builder.html", {"page": "builder", "version": __version__})

    @app.get("/profile", include_in_schema=False)
    def profile_page(request: Request):
        return templates.TemplateResponse(request, "profile.html", {"page": "profile", "version": __version__})

    app.include_router(public)
    app.include_router(api)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error path=%s", request.url.path)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    return app


app = create_app()
