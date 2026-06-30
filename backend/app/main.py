from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers.memory import router as memory_router
from app.routers.repos import router as repos_router

logger = logging.getLogger(__name__)

app = FastAPI(title="The Best Man", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repos_router)
app.include_router(memory_router)


def _flatten_included_routers() -> None:
    """Normalize deferred FastAPI included routers into concrete app routes.

    FastAPI 0.138 stores ``_IncludedRouter`` placeholders in ``app.routes``.
    That works for request dispatch, but local route inspection becomes opaque
    and prints non-standard route objects instead of real paths. We keep the
    standard ``app.include_router(...)`` calls above, then replace only those
    placeholders with the already-defined concrete routes from our routers.
    """

    concrete_routes = [
        route
        for route in app.router.routes
        if route.__class__.__name__ != "_IncludedRouter"
    ]
    concrete_routes.extend(repos_router.routes)
    concrete_routes.extend(memory_router.routes)
    app.router.routes = concrete_routes
    app.router._mark_routes_changed()


_flatten_included_routers()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    logger.info(
        "request completed",
        extra={
            "path": request.url.path,
            "method": request.method,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}
