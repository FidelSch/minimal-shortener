import random
import string

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl

app = FastAPI(title="URL Shortener")

_store: dict[str, str] = {}


class ShortenRequest(BaseModel):
    url: HttpUrl


class ShortenResponse(BaseModel):
    short_code: str
    short_url: str


def _generate_code(length: int = 6) -> str:
    chars = string.ascii_letters + string.digits
    while True:
        code = "".join(random.choices(chars, k=length))
        if code not in _store:
            return code


@app.post("/shorten", response_model=ShortenResponse, status_code=201)
def shorten_url(body: ShortenRequest):
    code = _generate_code()
    _store[code] = str(body.url)
    return ShortenResponse(short_code=code, short_url=f"/{code}")


@app.get("/{short_code}")
def redirect(short_code: str):
    url = _store.get(short_code)
    if url is None:
        raise HTTPException(status_code=404, detail="Short code not found")
    return RedirectResponse(url=url, status_code=302)
