"""DQ Sentinel — FastAPI application entry point."""

import os
import time
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from controllers.auth_controller import router as auth_router
from controllers.dashboard_controller import router as dashboard_router
from controllers.connector_controller import router as connector_router
from controllers.dataset_controller import router as dataset_router
from controllers.monitoring_controller import router as monitoring_router
from controllers.alert_controller import router as alert_router
from controllers.notification_controller import router as notif_router
from controllers.azure_controller import router as azure_router
from controllers.databricks_controller import router as databricks_router
from controllers.github_controller import router as github_router
from controllers.ai_controller import router as ai_router
from controllers.settings_controller import router as settings_router
from controllers.rule_book_controller import router as rule_book_router
from scheduler.monitoring_scheduler import start_scheduler, shutdown_scheduler
from utils.chroma_helper import init_chroma
from utils.common import logger

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DQ Sentinel starting up...")

    # Initialize Chroma DB
    try:
        init_chroma()
        logger.info("Chroma DB initialized")
        # Give a small delay for model to finish downloading
        time.sleep(1)
    except Exception as e:
        logger.warning("Chroma DB initialization failed (optional): %s", e)

    start_scheduler()
    yield
    shutdown_scheduler()
    logger.info("DQ Sentinel shutting down...")


app = FastAPI(
    title="DQ Sentinel — Enterprise Data Observability Platform",
    version="1.0.0",
    description="AI-powered data quality, governance, and cloud monitoring.",
    lifespan=lifespan,
)

# origins = [
#     o.strip()
#     for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
#     if o.strip()
# ]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"app": "DQ Sentinel", "status": "running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}


# Routers
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(connector_router)
app.include_router(dataset_router)
app.include_router(monitoring_router)
app.include_router(alert_router)
app.include_router(notif_router)
app.include_router(azure_router)
app.include_router(databricks_router)
app.include_router(github_router)
app.include_router(ai_router)
app.include_router(settings_router)
app.include_router(rule_book_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=False,
    )
