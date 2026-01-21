from fastapi import FastAPI, Request
import datetime
import logging
import time
from app.api.query import router as query_router


# --- Logging config ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("query_service")

app = FastAPI(
    title="Rag Query Service",
    description="Service for querying a vector database",
    version="0.1.0",
    contact={"name": "Ali", "email": "ali@example.com"},
)


# Simple HTTP request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000

    logger.info(
        "HTTP request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        },
    )
    return response


app.include_router(query_router, tags=["Query"])


@app.get("/health", tags=["health"])
def health_check():
    return {
        "status": "ok",
        "service": "rag-query-service",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"),
    }
