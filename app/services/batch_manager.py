import asyncio
import time
from collections import deque
import httpx
from fastapi import HTTPException

from app.services.redis_pool import get_redis_pool

BATCH_MAX_SIZE = 4
BATCH_TIMEOUT = 0.5 # 500ms

class BatchRequest:
    def __init__(self, request_data: dict):
        self.request_data = request_data
        self.response_future = asyncio.Future()

class BatchManager:
    def __init__(self):
        self.queue = deque()
        self.lock = asyncio.Lock()
        self._background_task = None
        self._last_batch_time = time.monotonic()
    
    async def add_request_to_queue(self, request_data: dict):
        batch_request = BatchRequest(request_data)
        async with self.lock:
            if len(self.queue) == 0:
                # Reset timer when adding first request to empty queue
                self._last_batch_time = time.monotonic()
            self.queue.append(batch_request)
        return batch_request.response_future
    
    async def _send_batch_to_worker(self, batch: list[BatchRequest]):
        redis = get_redis_pool()
        worker_url = await redis.brpoplpush('idle_workers', 'busy_workers', timeout=5)

        if not worker_url:
            exception = HTTPException(503, "Service temporarily unavailable. No workers.")
            for req in batch:
                req.response_future.set_exception(exception)
            return

        try: 
            # Process batch one by one for now (llama.cpp server doesn't support batch completion)
            results = []
            for req in batch:
                formatted_prompt = f"User: {req.request_data['messages'][-1]['content']}\nAssistant:"
                
                payload = {
                    "prompt": formatted_prompt,  # llama.cpp accepts string prompt
                    "n_predict": 128,
                    "stop": ["\nUser:", "</s>", "<end_of_turn>"],
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "stream": False,  # Ensure we get complete response
                    "cache_prompt": True  # Enable prompt caching for better performance
                }

                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(f"{worker_url}/completion", json=payload)
                    response.raise_for_status()
                    result = response.json()
                    # llama.cpp returns content field directly in the response
                    content = result.get('content', '').strip()
                    
                    # Return the response in a consistent format
                    results.append({
                        "content": content,
                        "model": result.get('model', 'unknown'),
                        "tokens_predicted": result.get('tokens_predicted', 0),
                        "tokens_evaluated": result.get('tokens_evaluated', 0),
                        "stop": result.get('stop', False),
                        "stop_type": result.get('stop_type', 'unknown')
                    })

            # Set results for each request in the batch
            for i, req in enumerate(batch):
                if i < len(results):
                    req.response_future.set_result(results[i])
                else:
                    # Fallback response if somehow we don't have enough results
                    req.response_future.set_result({
                        "content": "",
                        "model": "unknown",
                        "tokens_predicted": 0,
                        "tokens_evaluated": 0,
                        "stop": True,
                        "stop_type": "error"
                    })
        except Exception as e:
            exception = HTTPException(500, f"Worker failed: {str(e)}")
            for req in batch:
                if not req.response_future.done():
                    req.response_future.set_exception(exception)
        finally:
            await redis.lrem("busy_workers", 1, worker_url)
            await redis.lpush("idle_workers", worker_url)
    
    async def _batch_processor_loop(self):
        while True:
            should_process = False
            current_time = time.monotonic()
            
            async with self.lock:
                if len(self.queue) >= BATCH_MAX_SIZE:
                    should_process = True
                elif self.queue and (current_time - self._last_batch_time) >= BATCH_TIMEOUT:
                    should_process = True
                
                if should_process:
                    num_to_process = min(len(self.queue), BATCH_MAX_SIZE)
                    batch = [self.queue.popleft() for _ in range(num_to_process)]
                    self._last_batch_time = current_time
                else:
                    batch = []

            if batch:
                asyncio.create_task(self._send_batch_to_worker(batch))

            await asyncio.sleep(0.1)   

    def start(self):
        if not self._background_task:
            self._background_task = asyncio.create_task(self._batch_processor_loop())
    
    async def stop(self):
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass

batch_manager = BatchManager()