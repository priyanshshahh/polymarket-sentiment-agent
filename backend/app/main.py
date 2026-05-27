"""FastAPI entry point. Spins up the DB and the agent loop."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router as api_router
from .config import settings
from .database import init_db
from .orchestrator import agent_loop

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("DB initialized; trading_mode=%s", settings.trading_mode)
    agent_loop.start()
    try:
        yield
    finally:
        await agent_loop.stop()


app = FastAPI(
    title="DOA Agent — Polymarket Sentiment Trader",
    version="0.1.0",
    description="Modular MVP: Scout -> Quant -> Oracle -> Trader, with Overseer gating.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/healthz")
def healthz():
    return {"ok": True, "mode": settings.trading_mode}
