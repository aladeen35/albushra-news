"""HTTP entry point: the API, the static frontend and basic protections."""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, public
from .config import get_settings
from .db import SessionLocal, init_db
from .seed import seed

FRONTEND = Path(os.environ.get("FRONTEND_DIR",
                               Path(__file__).resolve().parents[2] / "frontend"))


class RateLimiter:
    """Sliding window per client IP, in process.

    Good for one API instance. Behind several instances, move this to Redis
    so the limit is shared.
    """

    def __init__(self):
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)

    def allow(self, key: tuple[str, str], limit: int, window: float = 60.0) -> bool:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True


limiter = RateLimiter()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as session:
        seed(session)
    if get_settings().scheduler_enabled:
        from .scheduler import start
        start()
    yield


app = FastAPI(title="Al-Bushra News — البشرى للأخبار", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
app.include_router(public.router)
app.include_router(admin.router)
app.include_router(admin.auth_router)

CSP = ("default-src 'self'; img-src 'self' data: https:; style-src 'self'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


@app.middleware("http")
async def protect(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/docs"):
        settings = get_settings()
        ip = request.client.host if request.client else "unknown"
        bucket, limit = (("search", settings.search_rate_limit_per_minute)
                         if path.startswith("/api/search") or request.query_params.get("q")
                         else ("api", settings.rate_limit_per_minute))
        if not limiter.allow((ip, bucket), limit):
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429,
                                headers={"Retry-After": "60"})
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "DENY")
    if not path.startswith("/api/docs"):
        response.headers.setdefault("Content-Security-Policy", CSP)
    if path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


if FRONTEND.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")
    app.mount("/i18n", StaticFiles(directory=FRONTEND / "i18n"), name="i18n")

    @app.get("/admin", include_in_schema=False)
    def admin_entry():
        """A plain address for editors: /admin opens the sign-in page."""
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/#/admin", status_code=302)

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str):
        """Static files by name, everything else falls through to the SPA shell."""
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = (FRONTEND / path).resolve()
        if path and candidate.is_file() and FRONTEND.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(FRONTEND / "index.html")
