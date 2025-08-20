# VLM-GPT: High-Performance LLM Serving Gateway

## Project Description
This project provides a high-performance, scalable API gateway for serving local Large Language Models (LLMs). It uses a sophisticated batching mechanism to group concurrent client requests, processing them efficiently with one or more `llama.cpp` workers. The architecture is designed to maximize throughput and resource utilization for GGUF-compatible models (e.g., Gemma, Llama 3, Qwen).

At its core, the system uses FastAPI for the asynchronous API, Redis for high-speed coordination and service discovery, and Docker for containerization, creating a robust and scalable serving solution.

## Project Workflow & Flow Diagram

The system follows a coordinated, multi-stage workflow designed for efficiency and scalability using Redis for robust queue management.

```
                               +---------------------------------+
                               |      API Gateway (FastAPI)      |
                               | (POST /v1/predict -> Enqueue)   |
                               | (GET /v1/predict/{id} -> Result)|
                               +---------------------------------+
                                                |
+--------------------------------------------------------------------------------------------------+
|                                              Redis                                               |
|                                                                                                  |
|  +------------------------+  1. LPUSH   +------------------------+  2. BRPOPLPUSH  +-------------------------+  |
|  | User/Client            |----------->|   vlm_request_queue    |--------------->|   vlm_processing_queue  |  |
|  +------------------------+             +------------------------+                 +-------------------------+  |
|                                                                                                  | 3. Batch Processor
|                                                                                                  |    gets batch
|  +------------------------+  8. GET     +------------------------+                                 |
|  | User/Client            |<-----------|    vlm_result:{id}     |                                 |
|  +------------------------+  7. SETEX   +------------------------+                                 |
|                                 ^                                                                |
|                                 |                                                                v
|  +------------------------+     |      +------------------------+      +-------------------------+  |
|  | Worker                 |<----|------|      Batch Processor     |----->| idle/busy worker lists  |  |
|  | (llama.cpp)            | 6. Process |      (in API service)    | 4. Lease|                         |  |
|  +------------------------+    Batch   +------------------------+   Worker +-------------------------+  |
|                                 |                                      ^                           |
|                                 +--------------------------------------+ 5. Return Worker            |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+

```

### Workflow Steps:

1.  **Initialization**:
    *   `docker-compose up` launches the `api`, `redis`, and one or more `worker` services.
    *   Each `worker` starts a `llama-server` and registers its unique URL in the `idle_workers` list in Redis.
    *   The `api` service starts the `QueueProcessor` background task.

2.  **Client Request**:
    *   A client sends a prediction request to the `/v1/predict` endpoint.
    *   The API gateway calls the `RedisQueueManager` to push the request payload into the `vlm_request_queue` list in Redis.
    *   The gateway immediately returns a unique `request_id` to the client.

3.  **Batch Formation**:
    *   The `QueueProcessor`'s background loop continuously attempts to build a batch.
    *   It uses the `BRPOPLPUSH` command to atomically pop requests from `vlm_request_queue` and push them to a `vlm_processing_queue`. This ensures that even if the service restarts, requests are not lost.
    *   A batch is formed when either of two conditions is met:
        *   **Size:** The number of requests reaches `BATCH_MAX_SIZE`.
        *   **Timeout:** A `BATCH_TIMEOUT_MS` has elapsed.

4.  **Worker Leasing**:
    *   Once a batch is formed, the `QueueProcessor` leases a worker by atomically popping a worker URL from `idle_workers` and pushing it to `busy_workers`.

5.  **Dispatch & Inference**:
    *   The `QueueProcessor` sends the entire batch of requests to the leased worker's `/completion` endpoint.
    *   The worker's `llama-server` processes the batch and returns the results.

6.  **Store Results & Release Worker**:
    *   For each result in the response, the `QueueProcessor` stores it in Redis using a unique key (`vlm_result:{request_id}`).
    *   The corresponding request is removed from the `vlm_processing_queue`.
    *   The worker's URL is pushed back into the `idle_workers` list, making it available for the next batch.

7.  **Client Retrieval**:
    *   The client uses its `request_id` to poll the `/v1/predict/{request_id}` endpoint until the result is available and returned.

8.  **Cleanup**:
    *   A background cleanup task requeues any requests that have been in the `vlm_processing_queue` for too long, preventing stuck jobs.