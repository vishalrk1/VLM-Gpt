import asyncio
import time
import httpx
import logging

from app.services.redis_pool import redis_queue_manager, get_redis_pool

logger = logging.getLogger(__name__)

BATCH_MAX_SIZE = 8
BATCH_TIMEOUT_MS = 1000
PROCESSING_INTERVAL = 0.1 

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
        3. Only process if workers are available
        """
        while self._running:
            try:
                idle_workers = await self.redis.llen('idle_workers')
                
                if idle_workers > 0:
                    batch = await redis_queue_manager.dequeue_batch_with_timeout(
                        batch_size=BATCH_MAX_SIZE,
                        timeout_ms=BATCH_TIMEOUT_MS
                    )
                    
                    if batch:
                        asyncio.create_task(self._process_batch(batch))
                        logger.debug(f"Dispatched batch of {len(batch)} requests to available worker")
                else:
                    logger.debug("No idle workers available, waiting...")
                    await asyncio.sleep(0.5)
                    continue
                
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
        """
        Process a batch of requests concurrently using an available worker.
        Flow: request_queue -> processing_queue -> worker (concurrent processing)
        """
        start_time = time.time()
        worker_url = await self.redis.brpoplpush('idle_workers', 'busy_workers', timeout=5)

        try:
            if not worker_url:
                logger.warning(f"No worker available for batch of {len(batch)} requests, re-queuing")
                for request in batch:
                    await redis_queue_manager.enqueue_request(request["data"], request["id"])
                return

            logger.info(f"Worker {worker_url} processing batch of {len(batch)} requests concurrently")
            for request in batch:
                pass
            
            async def process_single_request(request):
                request_id = request["id"]
                request_data = request["data"]
                
                try:
                    result = await self._send_to_worker(worker_url, request_data)
                    await redis_queue_manager.store_result(request_id, result)
                    logger.debug(f"Request {request_id} completed successfully")
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
            
            await asyncio.gather(*[process_single_request(request) for request in batch])

        finally:
            if worker_url:
                await self.redis.lrem("busy_workers", 1, worker_url)
                await self.redis.lpush("idle_workers", worker_url)
                logger.debug(f"Worker {worker_url} released back to idle pool")
            
            processing_time = (time.time() - start_time) * 1000
            logger.info(f"Batch of {len(batch)} requests completed in {processing_time:.2f}ms (avg: {processing_time/len(batch):.2f}ms per request)")

    async def _send_to_worker(self, worker_url: str, request_data: dict) -> dict:
        temperature = request_data.get('temperature', 0.7)
        top_p = request_data.get('top_p', 0.9)
        n_predict = request_data.get('n_predict', 128)
        system_prompt = request_data.get('system_prompt', '')
        messages = request_data.get('messages', [])
    
        prompt_parts = []
        image_data = []  # Store image data for multimodal requests
        image_id_counter = 1
        
        if system_prompt:
            prompt_parts.append(f"System: {system_prompt}")
        
        # Add conversation history
        for message in messages:
            role = message.get('role', 'user')
            content = message.get('content', '')
            
            # Handle multimodal content
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if item.get('type') == 'text':
                        text_parts.append(item.get('text', ''))
                    elif item.get('type') == 'image_url':
                        image_url = item.get('image_url', {}).get('url', '')
                        if image_url.startswith('data:image/'):
                            try:
                                mime_part, base64_data = image_url.split(',', 1)
                                image_data.append({
                                    "data": base64_data,
                                    "id": image_id_counter
                                })
                                text_parts.append(f'[img-{image_id_counter}]')
                                image_id_counter += 1
                            except ValueError:
                                text_parts.append('[Image]')
                content = ' '.join(text_parts)
            
            if role == 'system' and not system_prompt:
                prompt_parts.insert(0, f"System: {content}")
            elif role == 'user':
                prompt_parts.append(f"User: {content}")
            elif role == 'assistant':
                prompt_parts.append(f"Assistant: {content}")
        
        formatted_prompt = "\n".join(prompt_parts) + "\nAssistant:"
        
        payload = {
            "prompt": formatted_prompt,
            "n_predict": n_predict,
            "stop": ["\nUser:", "</s>", "<end_of_turn>"],
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
            "cache_prompt": True
        }
        
        # Add image data if present (for multimodal requests)
        if image_data:
            payload["image_data"] = image_data

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