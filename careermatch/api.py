import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .matching import match
from .models import MatchRequest, MatchResponse

ROOT = Path(__file__).parent
app = FastAPI(title="CareerMatch Engine", version="0.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
# Bound CPU/memory work per process. Intended for local use behind loopback.
slots = asyncio.Semaphore(2)


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "mode": "local-demo", "storage": "request-scoped-in-memory"}


@app.get("/api/demo", response_model=MatchRequest)
def demo():
    return json.loads((ROOT / "fixtures" / "demo.json").read_text(encoding="utf-8"))


@app.post("/api/match", response_model=MatchResponse)
async def run_match(request: MatchRequest):
    try:
        async with slots:
            return await asyncio.to_thread(match, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
