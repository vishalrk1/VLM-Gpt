import asyncio
import time
import httpx
import logging

from app.services.redis_pool import redis_queue_manager, get_redis_pool

logger = logging.getLogger(__name__)

BATCH_MAX_SIZE = 4
BATCH_TIMEOUT_MS = 500  # 500ms timeout
PROCESSING_INTERVAL = 0.1  # Check for new requests every 100ms

class QueueProcessor:
    def __init__(self):
        self.redis = get_redis_pool()
        self._processor_task = None
        self._cleanup_task = None
        self._running = False

    async def start(self):
        if not self._processor_task:
            self._running = True
            self._processor_task = asyncio.create_task(self._process_queue_loop())
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Queue processor started with batch processing logic")

    async def stop(self):
        if self._processor_task:
            self._running = False
            self._processor_task.cancel()
            self._cleanup_task.cancel()
            try:
                await self._processor_task
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Queue processor stopped")

    async def _process_queue_loop(self):
        """
        Main processing loop with dual batch conditions:
        1. Process when batch reaches BATCH_MAX_SIZE
        2. Process after BATCH_TIMEOUT_MS even if batch is smaller
        """
        while self._running:
            try:
                batch = await redis_queue_manager.dequeue_batch_with_timeout(
                    batch_size=BATCH_MAX_SIZE,
                    timeout_ms=BATCH_TIMEOUT_MS
                )
                
                if batch:
                    batch_size = len(batch)
                    if batch_size == BATCH_MAX_SIZE:
                        logger.info(f"Processing FULL batch of {batch_size} requests")
                    else:
                        logger.info(f"Processing TIMEOUT batch of {batch_size} requests (waited {BATCH_TIMEOUT_MS}ms)")
                    asyncio.create_task(self._process_batch(batch))
                await asyncio.sleep(PROCESSING_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in queue processing loop: {e}")
                await asyncio.sleep(1)

    async def _cleanup_loop(self):
        """Cleanup failed requests every 30 seconds"""
        while self._running:
            try:
                await redis_queue_manager.requeue_failed_requests()
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(30)

    async def _process_batch(self, batch: list):
        worker_url = await self.redis.brpoplpush('idle_workers', 'busy_workers', timeout=5)

        if not worker_url:
            logger.warning(f"No workers available, re-queuing {len(batch)} requests")
            for request in batch:
                await redis_queue_manager.enqueue_request(request["data"], request["id"])
                await redis_queue_manager.mark_request_completed(request["id"])
            return

        try:
            logger.info(f"Worker {worker_url} processing batch of {len(batch)} requests")
            
            for request in batch:
                request_id = request["id"]
                request_data = request["data"]
                
                try:
                    result = await self._send_to_worker(worker_url, request_data)
                    await redis_queue_manager.store_result(request_id, result)
                    logger.info(f"Completed request {request_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to process request {request_id}: {e}")
                    error_result = {
                        "content": f"Error processing request: {str(e)}",
                        "tokens_predicted": 0,
                        "tokens_evaluated": 0,
                        "stop": True,
                        "stop_type": "error"
                    }
                    await redis_queue_manager.store_result(request_id, error_result)

        finally:
            await self.redis.lrem("busy_workers", 1, worker_url)
            await self.redis.lpush("idle_workers", worker_url)
            logger.info(f"Worker {worker_url} returned to idle pool")

    async def _send_to_worker(self, worker_url: str, request_data: dict) -> dict:
        formatted_prompt = f"User: {request_data['messages'][-1]['content']}\nAssistant:"
        
        payload = {
            "prompt": formatted_prompt,
            "n_predict": 128,
            "stop": ["\nUser:", "</s>", "<end_of_turn>"],
            "temperature": 0.7,
            "top_p": 0.9,
            "stream": False,
            "cache_prompt": True
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{worker_url}/completion", json=payload)
            response.raise_for_status()
            result = response.json()
            
            content = result.get('content', '').strip()
            
            return {
                "content": content,
                "tokens_predicted": result.get('tokens_predicted', 0),
                "tokens_evaluated": result.get('tokens_evaluated', 0),
                "stop": result.get('stop', False),
                "stop_type": result.get('stop_type', 'unknown')
            }

queue_processor = QueueProcessor()