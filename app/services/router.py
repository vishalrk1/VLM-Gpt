from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
import asyncio
import time
import uuid

from app.services.redis_pool import redis_queue_manager

router = APIRouter(prefix="/v1")

class Message(BaseModel):
    role: Literal["user", "assistant", "system"] = Field(..., description="Role of the message sender")
    content: str = Field(..., description="Content of the message")

class ChatRequest(BaseModel):
    model: str = Field(..., description="Model name to use for prediction")
    messages: List[Message] = Field(..., description="List of chat messages")
    request_id: Optional[str] = Field(None, description="Optional request ID (UUID will be generated if not provided)")

class ChatResponse(BaseModel):
    content: str = Field(..., description="Model's response content")
    tokens_predicted: int = Field(..., description="Number of tokens predicted")
    tokens_evaluated: int = Field(..., description="Number of tokens evaluated")
    stop: bool = Field(..., description="Whether the model stopped generation")
    stop_type: Optional[str] = Field(None, description="Type of stop event")
    request_id: str = Field(..., description="Request ID for tracking")

@router.post("/predict", response_model=ChatResponse)
async def predict(req: ChatRequest):
    request_id = req.request_id or str(uuid.uuid4())
    
    request_data = req.model_dump()
    request_data.pop('request_id', None)
    
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