# VLM-GPT: High-Performance LLM Serving Gateway

A scalable, containerized API gateway for local LLMs (GGUF models) with efficient batching, FastAPI, Redis, and Docker.

**Key Features:**
- **Batching** maximizes throughput
- **Redis** manages queues and worker states  
- **Docker** enables easy scaling
- **Multimodal** text+image support
- **GPU acceleration** with CUDA

## System structure

![System Architecture Overview](./diagrams/architecture.png)
*Figure: High-level architecture (API layer, Redis, worker pools, GPU nodes).*
<img width="935" height="555" alt="image" src="https://github.com/user-attachments/assets/48e9f6db-eebf-4c48-8963-3262dbfb41cd" />

## Performance Benchmarks

The system has been tested with comprehensive benchmarks designed for a 2-worker configuration:

### System configurations
- 2-worker setup
- 16GB Memory used
- GPU [ Nvidia RTX 3070 ]

## Benchmark Results Overview

### Gemma 3 4B 

| Test Case | Duration (s) | Requests | Success Rate | RPS | Avg Latency (s) | P95 Latency (s) | Tokens/s |
|-----------|---------------|----------|--------------|-----|-----------------|-----------------|----------|
| Burst Load (10req/1s) | 20.76 | 10 | 100% | 0.48 | 19.07 | 20.76 | 38.53 |
| Sustained Load (2req/s×15s) | 176.96 | 30 | 100% | 0.17 | 65.40 | 113.49 | 25.14 |
| Ramp-up Load (1→8req/s) | 340.37 | 64 | 100% | 0.19 | 20.77 | 33.99 | 27.40 |
| Stress Test (20 concurrent) | 102.76 | 20 | 100% | 0.19 | 54.56 | 102.76 | 23.74 |
| Image Burst (12 concurrent) | 13.19 | 11 | 100% | 0.83 | 9.16 | 13.19 | 30.78 |
| Adaptive Concurrency Sweep | 288.75 | 62 | 100% | 0.21 | 41.70 | 83.87 | 29.29 |

### Qwen 3 8B

| Test Case | Duration (s) | Requests | Success Rate | RPS | Avg Latency (s) | P95 Latency (s) | Tokens/s |
|-----------|---------------|----------|--------------|-----|-----------------|-----------------|----------|
| Burst Load (10req/1s) | 42.00 | 10 | 100% | 0.24 | 38.38 | 42.00 | 19.05 |
| Sustained Load (2req/s×15s) | 254.55 | 30 | 33% | 0.12 | 64.38 | 103.52 | 3.71 |
| Ramp-up Load (1→8req/s) | 861.20 | 64 | 98% | 0.07 | 33.91 | 67.75 | 10.66 |
| Stress Test (20 concurrent) | 240.68 | 20 | 50% | 0.08 | 38.17 | 52.57 | 2.08 |
| Image Burst (12 concurrent) | 62.19 | 11 | 100% | 0.18 | 43.87 | 62.18 | 14.92 |
| Adaptive Concurrency Sweep | 599.35 | 62 | 90% | 0.10 | 58.02 | 111.96 | 11.44 |

**Test Case Details:**
- **Burst Load Test**: Sends 10 requests simultaneously within 1 second to test burst handling capacity and initial system responsiveness
- **Sustained Load Test**: Maintains steady 2 requests/second for 15 seconds to evaluate consistent performance under optimal worker utilization  
- **Ramp-up Load Test**: Gradually increases from 1 to 8 requests/second over 15 seconds to identify throughput scaling behavior and saturation points
- **Stress Test**: Launches 20 concurrent requests simultaneously to test system limits, queue handling, and error recovery under extreme load
 - **Image Burst (12 concurrent)**: Issues 12 concurrent image+text requests to assess multimodal throughput and latency under burst pressure
 - **Adaptive Concurrency Sweep**: Gradually sweeps concurrency levels to chart throughput vs. latency and identify the saturation knee point
