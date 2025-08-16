import redis.asyncio as redis
from functools import lru_cache
import time
import json
from app.config import settings
from typing import Dict, Any, Optional, List

@lru_cache()
def get_redis_pool():
    return redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )

class RedisQueueManager:
    def __init__(self):
        self.redis = get_redis_pool()
        self.request_queue = "vlm_request_queue"
        self.processing_queue = "vlm_processing_queue"
        self.result_prefix = "vlm_result:"
        self.batch_lock = "vlm_batch_lock"
    
    async def enqueue_request(self, request_data: Dict[str, Any], request_id: str):
        payload = {
            "id": request_id,
            "data": request_data,
            "timestamp": int(time.time() * 1000),
            "retry_count": 0
        }

        await self.redis.lpush(self.request_queue, json.dumps(payload))
        return request_id
    
    async def dequeue_batch_with_timeout(self, batch_size: int = 4, timeout_ms: int = 500) -> List[Dict]:
        """
        1. process imidiately when batch is full (batch_size items)
        2. process after timeout (timeout_ms) even if batch is not full
        """
        batch = []
        start_time = time.time() * 1000

        while len(batch) < batch_size:
            elapsed_time = (time.time() * 1000) - start_time
            remaining_timeout = max(0, timeout_ms - elapsed_time)

            if remaining_timeout <=0 and batch:
                break

            result = await self.redis.brpoplpush(
                self.request_queue,
                self.processing_queue,
                timeout=max(0.5, remaining_timeout / 1000)  # Convert to seconds
            )

            if result:
                batch.append(json.loads(result))
                if len(batch) == batch_size:
                    break
            else:
                if batch:
                    break
                else:
                    continue
        return batch
    
    async def store_result(self, request_id: str, result: Dict[str, Any]):
        result_key = f"{self.result_prefix}{request_id}"
        await self.redis.setex(
            result_key, 
            300, 
            json.dumps(result)
        )

    async def get_result(self, request_id: str) -> Optional[Dict[str, Any]]:
        result_key = f"{self.result_prefix}{request_id}"
        result = await self.redis.get(result_key)
        return json.loads(result) if result else None
    
    async def mark_request_completed(self, request_id: str):
        processing_items = await self.redis.lrange(self.processing_queue, 0, -1)
        
        for item in processing_items:
            request_data = json.loads(item)
            if request_data.get("id") == request_id:
                await self.redis.lrem(self.processing_queue, 1, item)
                break
    
    async def requeue_failed_requests(self):
        current_time = int(time.time() * 1000)
        processing_items = await self.redis.lrange(self.processing_queue, 0, -1)
        
        for item in processing_items:
            request_data = json.loads(item)
            if current_time - request_data["timestamp"] > 120000:
                request_data["retry_count"] += 1
                if request_data["retry_count"] < 2:  # Max 2 retries
                    await self.redis.lrem(self.processing_queue, 1, item)
                    await self.redis.rpush(self.request_queue, json.dumps(request_data))

    async def get_queue_stats(self) -> Dict[str, int]:
        return {
            "pending_requests": await self.redis.llen(self.request_queue),
            "processing_requests": await self.redis.llen(self.processing_queue),
            "idle_workers": await self.redis.llen("idle_workers"),
            "busy_workers": await self.redis.llen("busy_workers"),
            "total_workers": await self.redis.llen("idle_workers") + await self.redis.llen("busy_workers")
        }

redis_queue_manager = RedisQueueManager()