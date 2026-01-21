from fastapi import FastAPI
from app.api.ingest import router as ingest_router
import datetime


app = FastAPI(
    title="Rag Ingestion Service",
    description="Service for ingesting data into a vector database",
    version="0.1.0",
    contact={"name": "Ali", "email": "ali@example.com"},
)


app.include_router(ingest_router)


@app.get("/health", tags=["health"])
def health_check():
    return {
        "status": "ok",
        "service": "rag-ingestion-service",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"),
    }
