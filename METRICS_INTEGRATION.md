# VictoriaMetrics Integration for Python Worker

## Overview

The Python worker has been integrated with VictoriaMetrics monitoring using the InfluxDB Line Protocol. Metrics are sent asynchronously to a vmagent sidecar to avoid blocking the ZMQ event loop.

## Changes Made

### 1. Fixed `push_metrics.py`

**Key improvements:**
- Changed endpoint from `8428` to `8429` (vmagent port)
- Added proper InfluxDB Line Protocol formatting with timestamps
- Implemented two separate metrics: `worker_task_processed` (counter) and `worker_task_duration_ms` (gauge)
- Used hostname as `worker_id` for automatic identification
- Set timeout to 50ms (as required)
- Added proper type hints and documentation

**Metrics sent:**
```
worker_task_processed,worker_id=<hostname>,lang=python count=1 <timestamp_ns>
worker_task_duration_ms,worker_id=<hostname>,lang=python value=<duration> <timestamp_ns>
```

### 2. Updated `main.py`

**Integration changes:**
- Converted to async/await pattern using `asyncio`
- Created persistent `httpx.AsyncClient` for efficient connection reuse
- Added task timing measurement using `time.perf_counter()`
- **Implemented metrics batching** to handle high throughput (~6000 tasks/s)
- Batch flush triggers:
  - When buffer reaches 1000 metrics
  - OR when 1 second has passed since last flush
- Added final flush in `finally` block to prevent metric loss on worker termination

### 3. Updated `pyproject.toml`

**Added dependency:**
```toml
"httpx>=0.28.1"
```

### 4. Created `test_metrics.py`

A standalone test script to verify the metrics integration works correctly.

## Usage

### Install Dependencies

```bash
uv sync
```

### Start Infrastructure

```bash
docker-compose up -d
```

This starts:
- VictoriaMetrics (port 8428)
- vmagent (port 8429)

### Run the Worker

```bash
python main.py
```

### Test Metrics

```bash
python test_metrics.py
```

### View Metrics

Open VictoriaMetrics UI: http://localhost:8428

**Query examples:**
```promql
# Total tasks processed by Python workers
worker_task_processed{lang="python"}

# Task duration over time
worker_task_duration_ms{lang="python"}

# Average task duration (rate over 1 minute)
rate(worker_task_duration_ms{lang="python"}[1m])
```

## Architecture

```
┌─────────────┐
│   Python    │
│   Worker    │
│             │
│  main.py    │──┐
└─────────────┘  │
                 │ HTTP POST
                 │ (InfluxDB Line Protocol)
                 │ timeout: 50ms
                 ▼
            ┌─────────┐      ┌──────────────────┐
            │ vmagent │─────▶│ VictoriaMetrics  │
            │  :8429  │      │      :8428       │
            └─────────┘      └──────────────────┘
```

## Batching Strategy

To handle high throughput (~6000 tasks/s), metrics are batched before sending:

- **Buffer Size**: Collects up to 1000 metrics before flushing
- **Time-based Flush**: Flushes every 1 second even if buffer isn't full
- **Final Flush**: Ensures remaining metrics are sent when worker terminates
- **Performance**: Reduces HTTP requests from 6000/s to ~6/s (1000x improvement)

## Error Handling

- **Fire-and-forget**: Metrics failures don't interrupt task processing
- **Short timeout**: 100ms for batch requests
- **Silent failures**: Exceptions are caught and ignored
- **Non-blocking**: Async HTTP calls don't block ZMQ event loop
- **Graceful shutdown**: Final flush in `finally` block prevents data loss

## Metrics Details

### worker_task_processed

- **Type**: Counter
- **Description**: Incremented each time a task is completed
- **Tags**: 
  - `worker_id`: Hostname of the worker
  - `lang`: Always "python"
- **Field**: `count=1