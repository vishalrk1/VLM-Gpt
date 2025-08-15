from fastapi import APIRouter
from pydantic import BaseModel

from app.services.batch_manager import batch_manager

router = APIRouter(prefix="/v1")

class ChatReq(BaseModel):
    model: str
    messages: list[dict]

@router.post("/predict")
async def predict(req: ChatReq):
    response_future = await batch_manager.add_request_to_queue(req.model_dump())
    return await response_future