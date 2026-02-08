import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from starlette.responses import Response
from app.config import get_settings
from app.database import create_pool, close_pool, init_db
from app.circuit_breaker import CircuitBreaker
from app.submission_client import SubmissionClient
from app.kafka_consumer import start_consumer
from app.metrics import (
    REQUEST_COUNT,
    REQUEST_LATENCY,
    CIRCUIT_BREAKER_STATE,
    get_metrics_content,
    CONTENT_TYPE_LATEST,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown."""
    # Startup
    logger.info("Starting Catalog Service...")
    settings = get_settings()
    pool = await create_pool(settings)
    await init_db(pool)
    
    # Initialize submission client with circuit breaker
    cb = CircuitBreaker(
        max_failures=settings.cb_max_failures,
        reset_timeout=settings.cb_reset_timeout,
        call_timeout=settings.cb_call_timeout
    )
    submission_client = SubmissionClient(settings.submission_service_url, cb)
    
    # Store in app state
    app.state.pool = pool
    app.state.submission_client = submission_client
    app.state.settings = settings
    app.state.circuit_breaker = cb
    
    # Start Kafka consumer as background task
    consumer_task = asyncio.create_task(start_consumer(pool, settings))
    app.state.consumer_task = consumer_task
    
    logger.info("Catalog Service started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Catalog Service...")
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    
    await submission_client.close()
    await close_pool()
    logger.info("Catalog Service shut down complete")


app = FastAPI(
    title="Paper Catalog Service",
    description="Catalog service for paper management",
    version="0.1.0",
    lifespan=lifespan
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Middleware to collect request metrics."""
    import time
    start_time = time.time()
    
    try:
        response = await call_next(request)
        status = str(response.status_code)
    except Exception as e:
        status = "500"
        raise
    finally:
        duration = time.time() - start_time
        endpoint = request.url.path
        method = request.method
        
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)
    
    return response


@app.middleware("http")
async def circuit_breaker_metrics_middleware(request: Request, call_next):
    """Middleware to update circuit breaker metrics."""
    response = await call_next(request)
    
    if hasattr(request.app.state, "circuit_breaker"):
        cb = request.app.state.circuit_breaker
        state = cb.get_state()
        # Map state to numeric value: CLOSED=0, OPEN=1, HALF_OPEN=2
        state_value = {"CLOSED": 0, "OPEN": 1, "HALF_OPEN": 2}.get(state.value, 0)
        CIRCUIT_BREAKER_STATE.set(state_value)
    
    return response


@app.get("/api/v1/catalog")
async def list_papers(request: Request):
    """List all papers in catalog."""
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM catalog_papers ORDER BY synced_at DESC"
        )
    return [dict(r) for r in rows]


@app.get("/api/v1/catalog/{paper_id}")
async def get_paper(paper_id: str, request: Request):
    """Get paper by ID from catalog or submission service."""
    pool = request.app.state.pool
    
    # Try local DB first
    try:
        paper_uuid = uuid.UUID(paper_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid paper ID format")
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM catalog_papers WHERE id = $1",
            paper_uuid
        )
    
    if row:
        result = dict(row)
        result["source"] = "local_db"
        return result
    
    # Cache miss - try submission service (service-to-service call)
    client = request.app.state.submission_client
    remote_paper = await client.get_paper(paper_id)
    if remote_paper:
        remote_paper["source"] = "submission_service"
        return remote_paper
    
    raise HTTPException(status_code=404, detail="Paper not found")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "UP"}


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=get_metrics_content(),
        media_type=CONTENT_TYPE_LATEST
    )
