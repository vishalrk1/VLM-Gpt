from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.responses import JSONResponse
import logging

from app.services.router import router
from app.services.redis_pool import get_redis_pool
from app.services.batch_manager import queue_processor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = get_redis_pool()
    await redis.delete("idle_workers", "busy_workers")
    
    await queue_processor.start()
    logger.info("Application started with Redis queue processor")
    
    yield
    
    await queue_processor.stop()
    await redis.delete("idle_workers", "busy_workers")
    logger.info("Application stopped")

health_router = APIRouter()

@health_router.get("/health")
async def health():
    redis = get_redis_pool()
    idle = await redis.llen("idle_workers")
    busy = await redis.llen("busy_workers")
    total_workers = idle + busy
    
    if total_workers > 0:
        return JSONResponse({
            "status": "ok",
            "workers": {
                "idle": idle,
                "busy": busy,
                "total": total_workers
            }
        })
    return JSONResponse({
        "status": "no_workers",
        "workers": {
            "idle": 0,
            "busy": 0,
            "total": 0
        }
    }, status_code=503)

app = FastAPI(lifespan=lifespan)
app.include_router(router)
app.include_router(health_router)