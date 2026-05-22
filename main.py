import logging
import os
import random
import string
import time
from typing import Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Request, Response, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, HttpUrl
from prometheus_client import Counter, Histogram, CONTENT_TYPE_LATEST, generate_latest, Info
from redis.exceptions import RedisError

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
METRICS_TOKEN = os.getenv("METRICS_TOKEN", "")

_bearer = HTTPBearer()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("url_shortener")

app = FastAPI(title="URL Shortener")

_redis: Optional[aioredis.Redis] = None


class ShortenRequest(BaseModel):
    url: HttpUrl


class ShortenResponse(BaseModel):
    short_code: str
    short_url: str


REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "http_status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)
ERROR_COUNT = Counter(
    "http_error_responses_total",
    "Total HTTP error responses",
    ["status_code"],
)
EXCEPTIONS_COUNT = Counter(
    "http_exceptions_total",
    "Total unhandled HTTP exceptions",
    ["exception_type"],
)
REDIS_ERRORS = Counter(
    "redis_errors_total",
    "Total Redis errors",
    ["operation"],
)
APP_INFO = Info("app_info", "Application metadata")
APP_INFO.info({"name": "minimal-shortener", "version": "1.0"})


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        endpoint = self._endpoint_label(request)

        try:
            response = await call_next(request)
        except Exception as exc:
            EXCEPTIONS_COUNT.labels(exception_type=type(exc).__name__).inc()
            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=endpoint,
                http_status="500",
            ).inc()
            REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(
                time.time() - start_time
            )
            logger.exception("Unhandled exception during request")
            raise

        status_code = str(response.status_code)
        REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, http_status=status_code).inc()
        REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(time.time() - start_time)
        if response.status_code >= 400:
            ERROR_COUNT.labels(status_code=status_code).inc()
        return response

    @staticmethod
    def _endpoint_label(request: Request) -> str:
        route = request.scope.get("route")
        if route and hasattr(route, "path"):
            return route.path
        return request.url.path


app.add_middleware(MetricsMiddleware)


@app.on_event("startup")
async def startup() -> None:
    global _redis
    _redis = aioredis.from_url(REDIS_URL, decode_responses=True)


@app.on_event("shutdown")
async def shutdown() -> None:
    if _redis:
        await _redis.aclose()


def _generate_code(length: int = 6) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


@app.get("/metrics")
async def metrics(credentials: HTTPAuthorizationCredentials = Security(_bearer)) -> Response:
    if not METRICS_TOKEN or credentials.credentials != METRICS_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health() -> JSONResponse:
    if _redis is None:
        return JSONResponse(status_code=503, content={"status": "error", "reason": "redis-uninitialized"})

    try:
        pong = await _redis.ping()
    except RedisError:
        REDIS_ERRORS.labels(operation="ping").inc()
        return JSONResponse(status_code=503, content={"status": "error", "reason": "redis-unavailable"})

    if not pong:
        REDIS_ERRORS.labels(operation="ping").inc()
        return JSONResponse(status_code=503, content={"status": "error", "reason": "redis-unavailable"})

    return JSONResponse(status_code=200, content={"status": "ok", "redis": "connected"})


@app.post("/shorten", response_model=ShortenResponse, status_code=201)
async def shorten_url(body: ShortenRequest, request: Request):
    url = str(body.url)
    base_url = os.getenv("BASE_URL", str(request.base_url).rstrip("/"))
    for _ in range(10):
        code = _generate_code()
        try:
            if await _redis.set(f"url:{code}", url, nx=True):
                return ShortenResponse(short_code=code, short_url=f"{base_url}/{code}")
        except RedisError:
            REDIS_ERRORS.labels(operation="set").inc()
            raise HTTPException(status_code=503, detail="Redis unavailable")

    raise HTTPException(status_code=500, detail="Could not generate a unique code")


@app.get("/{short_code}")
async def redirect(short_code: str):
    try:
        url = await _redis.get(f"url:{short_code}")
    except RedisError:
        REDIS_ERRORS.labels(operation="get").inc()
        raise HTTPException(status_code=503, detail="Redis unavailable")

    if url is None:
        raise HTTPException(status_code=404, detail="Short code not found")

    return RedirectResponse(url=url, status_code=302)
