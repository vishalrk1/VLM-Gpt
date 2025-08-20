from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Union
import asyncio
import time
import uuid

from app.services.redis_pool import redis_queue_manager
from app.config import settings

router = APIRouter(prefix="/v1")

class ImageUrl(BaseModel):
    url: str = Field(..., description="Image URL or base64 data URI")

class ContentItem(BaseModel):
    type: Literal["text", "image_url"] = Field(..., description="Type of content")
    text: Optional[str] = Field(None, description="Text content")
    image_url: Optional[ImageUrl] = Field(None, description="Image URL content")

class Message(BaseModel):
    role: Literal["user", "assistant", "system"] = Field(..., description="Role of the message sender")
    content: Union[str, List[ContentItem]] = Field(..., description="Content of the message - can be string or list of content items for multimodal")

class ChatRequest(BaseModel):
    model: str = Field(..., description="Model name to use for prediction")
    messages: List[Message] = Field(..., description="List of chat messages")
    request_id: Optional[str] = Field(None, description="Optional request ID (UUID will be generated if not provided)")
    system_prompt: Optional[str] = Field(None, description="Optional system prompt to prepend to the conversation")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Controls randomness in generation (0.0-2.0)")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="Controls diversity of generation (0.0-1.0)")
    n_predict: Optional[int] = Field(None, ge=1, le=2048, description="Maximum number of tokens to generate")

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
    
    # Apply default values for optional parameters
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