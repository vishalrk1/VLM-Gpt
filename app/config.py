from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    redis_url: str = Field("redis://localhost:6379", env='REDIS_URL')
    worker_port_range: tuple[int, int] = (8001, 80018)
    model_path: str = "/models/<model.gguf>"
    max_context: int = 2049
    
    # Default generation parameters
    default_temperature: float = 0.7
    default_top_p: float = 0.9
    default_n_predict: int = 128
    default_system_prompt: str = ""

settings = Settings()