from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.responses import JSONResponse

from app.services.router import router
from app.services.redis_pool import get_redis_pool
from app.services.batch_manager import batch_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = get_redis_pool()
    await redis.delete("idle_workers", "busy_workers")
    batch_manager.start()
    yield
    await batch_manager.stop()
    await redis.delete("idle_workers", "busy_workers")

health_router = APIRouter()

@health_router.get("/health")
async def health():
    redis = get_redis_pool()
    idle = await redis.llen("idle_workers")
    busy = await redis.llen("busy_workers")
    if (idle + busy) > 0:
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "no_workers"}, status_code=503)

app = FastAPI(lifespan=lifespan)
app.include_router(router)
app.include_router(health_router)