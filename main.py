import os
import random
import string

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

app = FastAPI(title="URL Shortener")

_redis: aioredis.Redis | None = None


@app.on_event("startup")
async def startup() -> None:
    global _redis
    _redis = aioredis.from_url(REDIS_URL, decode_responses=True)


@app.on_event("shutdown")
async def shutdown() -> None:
    if _redis:
        await _redis.aclose()


class ShortenRequest(BaseModel):
    url: HttpUrl


class ShortenResponse(BaseModel):
    short_code: str
    short_url: str


def _generate_code(length: int = 6) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


@app.post("/shorten", response_model=ShortenResponse, status_code=201)
async def shorten_url(body: ShortenRequest):
    url = str(body.url)
    for _ in range(10):
        code = _generate_code()
        # SET NX -- only write if the key does not already exist
        if await _redis.set(f"url:{code}", url, nx=True):
            return ShortenResponse(short_code=code, short_url=f"/{code}")
    raise HTTPException(status_code=500, detail="Could not generate a unique code")


@app.get("/{short_code}")
async def redirect(short_code: str):
    url = await _redis.get(f"url:{short_code}")
    if url is None:
        raise HTTPException(status_code=404, detail="Short code not found")
    return RedirectResponse(url=url, status_code=302)
