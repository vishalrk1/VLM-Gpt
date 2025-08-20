# VLM-GPT: High-Performance LLM Serving Gateway

A scalable, containerized API gateway for local LLMs (GGUF models) with efficient batching, FastAPI, Redis, and Docker.

---

## Architecture & Workflow

Basic Flow Diagram:

```
    [Client]
         |
         v   (POST /v1/predict)
 [API Gateway]
         |
         v   (Enqueue)
     [Redis Queue]
         |
         v   (Batch)
 [QueueProcessor]
         |
         v   (Lease Worker)
     [Worker (llama.cpp)]
         |
         v   (Results)
     [Redis Result]
         ^
         |
         +--- (Client polls /v1/result/{id})
```

**Workflow Steps:**

1. **Client** sends a request to `/v1/predict`. API enqueues it in Redis and returns a `request_id`.
2. **QueueProcessor** forms batches from the queue, leases an idle worker, and dispatches the batch.
3. **Worker** (llama.cpp) processes the batch and stores results in Redis.
4. **Client** polls `/v1/result/{id}` to retrieve the result.
5. **Cleanup** ensures stuck requests are re-queued.

---

- **Batching** maximizes throughput.
- **Redis** manages queues and worker states.
- **Docker** enables easy scaling.
- **Supports multimodal (text+image) requests.**

---