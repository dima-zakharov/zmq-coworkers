Here is the fully revised, technically accurate `README.md` in English, updated with the **Apache License 2.0**.

---

# ZMQ PUSH/PULL Task Processing System

A high-performance, asynchronous distributed task processing system built on the ZeroMQ **PUSH/PULL** pattern. This "Coordinator-Worker" architecture enables seamless horizontal scaling, language-agnostic integration, and zero-registration worker management.

## Architecture

### PUSH/PULL Pattern
The system leverages PUSH and PULL sockets for automatic load balancing and decoupled data flow:



```text
Coordinator (Rust):
  ├─ PUSH socket → ipc:///tmp/benchmark-tasks.ipc (Task Distribution)
  └─ PULL socket ← ipc:///tmp/benchmark-results.ipc (Result Collection)

Workers (Python/Rust):
  ├─ PULL socket ← Receives tasks from Coordinator
  └─ PUSH socket → Sends results back to Coordinator
```

### Key Features
* **Zero Registration**: Workers connect and begin processing immediately without a handshake.
* **Dynamic Scaling**: Add or remove workers at runtime without restarting the Coordinator.
* **Language Agnostic**: Mix and match Python and Rust workers within the same network.
* **Automatic Load Balancing**: ZeroMQ distributes tasks to available workers via internal round-robin logic.
* **Stateless Design**: The Coordinator does not need to track worker IDs or the total worker count.

---

## Performance Benchmarks

### Rust Coordinator + Python Workers (1M tasks, 24 max in-flight)

Tested on **Linux (i5-12500H)**. The Rust Coordinator managed multiple external Python workers.

| Workers | Composition | Throughput (tasks/s) | Avg Latency (ms) | Gain |
| :--- | :--- | :--- | :--- | :--- |
| **1** | 1 Python | 57,935 | 0.412 | Baseline |
| **2** | 2 Python | **103,272** | **0.230** | **+78%** |
| **3** | 3 Python | **120,755** | **0.196** | **+108%** |

**Key Observations:**
* **Rust Efficiency**: The Rust core orchestrates high-volume distribution to Python workers with sub-millisecond overhead.
* **Horizontal Scaling**: Throughput increases significantly as more workers are added, until CPU saturation.
* **Hot-Plugging**: Workers were added mid-test and immediately began sharing the load.

---

## Why PUSH/PULL?

We transitioned to PUSH/PULL from ROUTER/DEALER to achieve a **stateless** transport layer:

| Feature | PUSH/PULL | ROUTER/DEALER |
| :--- | :--- | :--- |
| **Worker Identity** | **Anonymous** (Not needed) | **Stateful** (Must track IDs) |
| **Registration** | Not required | Mandatory for routing |
| **Complexity** | Low (Unidirectional flow) | High (Queue management) |
| **Startup Order** | **Flexible** (Any order) | Usually Coordinator first |

> **Note on Benchmarking**: In `coordinator-only` mode, the 2-second initial delay is used solely to stabilize performance metrics and is not a protocol requirement.

---

## Usage

### Quick Start

**1. Start Workers (any order):**
```bash
# Python workers
uv run main.py worker &
uv run main.py worker &

# Rust workers
./target/release/zmq-coworkers worker &
```

**2. Start Coordinator:**
```bash
# Recommended for maximum performance
./target/release/zmq-coworkers coordinator-only 1000000 24
```

### Command Arguments

**Rust Coordinator:**
`./target/release/zmq-coworkers coordinator-only [tasks] [max_in_flight]`
* `tasks`: Total tasks to process (e.g., `1000000`).
* `max_in_flight`: Semaphore limit for concurrent tasks (backpressure).

---

## Task Structure (JSON)
Task identification is handled at the **application layer** via UUIDs, as the PUSH/PULL transport is anonymous:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "payload": "...",
  "timestamp": "2026-04-29T10:30:00Z",
  "processed": false
}
```

## Requirements
* **Rust**: `tokio`, `zmq`, `serde_json`, `uuid`, `chrono`.
* **Python**: `pyzmq`, `orjson`, `pydantic`, `httpx`.

---

## Monitoring with VictoriaMetrics

The Python workers are integrated with VictoriaMetrics for performance monitoring.

### Metrics Collected

- **worker_task_processed**: Counter incremented for each completed task
- **worker_task_duration_ms**: Task processing latency in milliseconds

Both metrics include tags:
- `worker_id`: Hostname of the worker
- `lang`: Set to "python"

### Setup

1. Start VictoriaMetrics and vmagent:
```bash
docker-compose up -d
```

2. Workers automatically send metrics to vmagent at `http://localhost:8429/write`

3. View metrics at VictoriaMetrics UI: `http://localhost:8428`

### Query Examples

```promql
# Total tasks processed by Python workers
worker_task_processed{lang="python"}

# Task duration over time
worker_task_duration_ms{lang="python"}

# Average task duration (rate over 1 minute)
rate(worker_task_duration_ms{lang="python"}[1m])
```

See `METRICS_INTEGRATION.md` for detailed implementation information.

---
**License**: Apache License 2.0
