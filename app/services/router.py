from fastapi import APIRouter, HTTPException
import asyncio
import time
import uuid

from app.services.redis_pool import redis_queue_manager
from app.config import settings
from app.model import ChatRequest, ChatResponse

router = APIRouter(prefix="/v1")

@router.post("/predict", response_model=ChatResponse)
async def predict(req: ChatRequest):
    request_id = req.request_id or str(uuid.uuid4())
    
    request_data = req.model_dump()
    request_data.pop('request_id', None)
    
    request_data['system_prompt'] = req.system_prompt or settings.default_system_prompt
    request_data['temperature'] = req.temperature if req.temperature is not None else settings.default_temperature
    request_data['top_p'] = req.top_p if req.top_p is not None else settings.default_top_p
    request_data['n_predict'] = req.n_predict if req.n_predict is not None else settings.default_n_predict
    
    # Enqueue request
    await redis_queue_manager.enqueue_request(request_data, request_id)
    max_wait_time = 120
    poll_interval = 0.1
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        result = await redis_queue_manager.get_result(request_id)
        
        if result:
            await redis_queue_manager.mark_request_completed(request_id)
            result["request_id"] = request_id
            return ChatResponse(**result)
        
        await asyncio.sleep(poll_interval)

    await redis_queue_manager.mark_request_completed(request_id)
    raise HTTPException(status_code=408, detail=f"Request timeout for ID: {request_id}")

@router.get("/queue/stats")
async def get_queue_stats():
    return await redis_queue_manager.get_queue_stats()

@router.get("/result/{request_id}")
async def get_result(request_id: str):
    result = await redis_queue_manager.get_result(request_id)
    if result:
        result["request_id"] = request_id
        return ChatResponse(**result)
    raise HTTPException(status_code=404, detail="Result not found")