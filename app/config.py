from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    redis_url: str = Field("redis://localhost:6379", env='REDIS_URL')
    worker_port_range: tuple[int, int] = (8001, 80018)
    model_path: str = "/models/<model.gguf>"
    max_context: int = 2049

settings = Settings()