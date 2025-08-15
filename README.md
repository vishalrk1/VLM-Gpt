# VLM-GPT: High-Performance LLM Serving Gateway

## Project Description
This project provides a high-performance, scalable API gateway for serving local Large Language Models (LLMs). It uses a sophisticated batching mechanism to group concurrent client requests, processing them efficiently with one or more `llama.cpp` workers. The architecture is designed to maximize throughput and resource utilization for GGUF-compatible models (e.g., Gemma, Llama 3, Qwen).

At its core, the system uses FastAPI for the asynchronous API, Redis for high-speed coordination and service discovery, and Docker for containerization, creating a robust and scalable serving solution.

## Project Workflow & Flow Diagram

The system follows a coordinated, multi-stage workflow designed for efficiency and scalability.

```
+---------------------------+      +--------------------------------+      +--------------------------------+
|  User/Client Application  |----->|      API Gateway (FastAPI)     |----->|      BatchManager              |
+---------------------------+      |      (POST /v1/predict)        |      |  (In-Memory Queue & Logic)     |
                                   +--------------------------------+      +--------------------------------+
                                                  |                                      |
                                                  | 8. Resolves Future w/ Result         | 5. Triggers Batch (Size/Timeout)
                                                  |                                      |
                                                  +--------------------------------------+
                                                                                         |
                                                                                         v
+---------------------------+      +--------------------------------+      +--------------------------------+
|      Worker 1 (llama)     |<-----|         Redis Coordinator      |<-----|                                |
+---------------------------+      | (idle_workers, busy_workers)   |      |                                |
|      Worker 2 (llama)     |      +--------------------------------+      |                                |
+---------------------------+      |                                |      |                                |
|      ... Worker n ...     |----->| 9. Releases Worker             |----->| 6. Leases Worker (BRPOPLPUSH)  |
+---------------------------+      +--------------------------------+      +--------------------------------+
             ^                                                                           |
             | 7. Sends Batch for Inference                                              |
             +---------------------------------------------------------------------------+

```

### Workflow Steps:

1.  **Initialization**:
    *   `docker-compose up` launches the `api`, `redis`, and multiple `worker` services.
    *   Each worker starts a `llama-server` process and registers its unique, API-accessible URL in the `idle_workers` list in Redis.
    *   The FastAPI `api` service starts its `BatchManager` background loop.

2.  **Client Request**:
    *   A client sends a prediction request to the `/v1/predict` endpoint. The API hands the request to the `BatchManager`.

3.  **Queue & Future**:
    *   The `BatchManager` places the request into an internal, in-memory queue.
    *   It immediately returns an `asyncio.Future` object to the client's connection. The client now waits for this Future to be resolved.

4.  **Batch Trigger**:
    *   The `BatchManager`'s background loop continuously monitors the queue. A batch is formed and processed when one of two conditions is met:
        *   **Size:** The queue size reaches `BATCH_MAX_SIZE`.
        *   **Timeout:** A `BATCH_TIMEOUT` has elapsed since the first request entered the queue.

5.  **Worker Leasing**:
    *   The `BatchManager` performs a `BRPOPLPUSH` command on Redis. This is an atomic operation that pops a URL from `idle_workers` and pushes it to `busy_workers`, guaranteeing an exclusive "lease" on that worker.

6.  **Dispatch & Inference**:
    *   The `BatchManager` sends the entire batch of requests to the leased worker's `/completion` endpoint.
    *   The worker's `llama-server` processes the batch and returns the results.

7.  **Resolve & Release**:
    *   The `BatchManager` receives the results and resolves the corresponding `Future` for each request, which sends the response back to the waiting client.
    *   The worker's URL is removed from the `busy_workers` list and pushed back into `idle_workers`, making it available for the next batch.