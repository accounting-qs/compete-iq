import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.session import engine
from db.models import Base

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("CompeteIQ starting up")
    # Tables are managed by Alembic migrations — do not create_all here
    yield
    await engine.dispose()
    logger.info("CompeteIQ shut down")


app = FastAPI(
    title="CompeteIQ API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://competeiq-frontend-production.up.railway.app",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from api.routers import webhook, competitors, ads, generation
from api.routers.costs import router as costs_router

app.include_router(webhook.router, prefix="/webhook", tags=["webhook"])
app.include_router(competitors.router, prefix="/competitors", tags=["competitors"])
app.include_router(ads.router, prefix="/ads", tags=["ads"])
app.include_router(generation.router, prefix="/generate", tags=["generation"])
app.include_router(costs_router)

# Phase 1b — uncomment as built:
# from api.routers import outputs, brain, monitoring
# app.include_router(outputs.router, prefix="/outputs", tags=["outputs"])
# app.include_router(brain.router, prefix="/brain", tags=["brain"])
# app.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "competeiq"}
