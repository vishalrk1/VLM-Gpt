from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Union

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
