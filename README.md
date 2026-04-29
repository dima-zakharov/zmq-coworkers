# ZMQ Coordinator-Worker System

A high-performance asynchronous task processing system using ZeroMQ (ZMQ) with a coordinator-worker architecture.

## Architecture Overview

This application implements a distributed task processing system with the following components:

### Components

1. **Coordinator (Master)**
   - Manages task distribution to workers
   - Uses ZMQ ROUTER socket for bidirectional communication
   - Implements flow control using an asyncio Semaphore
   - Tracks task latencies and calculates throughput metrics

2. **Workers**
   - Process tasks independently in separate processes
   - Use ZMQ DEALER sockets to communicate with coordinator
   - Send "READY" signal on startup
   - Process tasks and return results

### Communication Flow

```
Coordinator (ROUTER) <--IPC--> Workers (DEALER)
         |
         |-- Spawns 6 worker processes
         |-- Distributes tasks round-robin
         |-- Controls max in-flight tasks via semaphore
         |-- Collects results and measures latency
```

### Key Features

- **Asynchronous I/O**: Uses asyncio for non-blocking operations
- **Flow Control**: Semaphore-based backpressure to limit concurrent tasks
- **IPC Communication**: Unix domain sockets for fast inter-process communication
- **Multiprocessing**: Spawns separate worker processes for parallel execution
- **Performance Metrics**: Tracks throughput (tasks/sec) and average latency (ms)

### Task Structure

Each task contains:
- Unique UUID identifier
- Payload (1500 character string)
- Metadata (20 key-value pairs with 20-char values)
- Timestamp
- Processing status flag

## Usage

```bash
uv run main.py coordinator <num_tasks> <max_in_flight>
```

### Parameters

- `coordinator`: Run in coordinator mode (required)
- `num_tasks`: Number of tasks to process (default: 50,000)
- `max_in_flight`: Maximum concurrent tasks allowed (default: 24)

### Examples

```bash
# Process 100 tasks with max 12 in-flight
uv run main.py coordinator 100 12

# Process 10,000 tasks with max 12 in-flight
uv run main.py coordinator 10000 12

# Process 1,000,000 tasks with max 12 in-flight
uv run main.py coordinator 1000000 12
```

## Performance Benchmarks i5-12500H

The following benchmarks were conducted with 6 workers processing 1,000,000 tasks with varying levels of concurrency (max in-flight tasks):

| Max In-Flight | Throughput (tasks/s) | Avg Latency (ms) |
|---------------|---------------------|------------------|
| 12            | 28,849.40           | 0.238            |
| 24            | 29,207.32           | 0.475            |
| 48            | 27,373.95           | 1.048            |
| 96            | 26,300.39           | 2.219            |

**Key Observations:**
- Peak throughput achieved at 24 concurrent tasks: ~29,200 tasks/s
- Latency increases proportionally with concurrency level
- Optimal balance between throughput and latency at 12-24 concurrent tasks
- Higher concurrency (48-96) shows diminishing returns with increased latency

*Note: Results measured on Linux system with 6 worker processes*

## How It Works

1. **Initialization**
   - Coordinator creates IPC socket and binds to `/tmp/benchmark.ipc`
   - Spawns 6 worker processes using multiprocessing
   - Workers connect to coordinator and send READY signal

2. **Task Distribution**
   - Coordinator generates all tasks upfront
   - Semaphore controls max concurrent tasks (backpressure)
   - Tasks distributed round-robin to workers
   - Each task send is tracked with timestamp

3. **Task Processing**
   - Workers receive tasks, mark as processed, update timestamp
   - Workers send results back to coordinator
   - Coordinator releases semaphore slot on result receipt

4. **Metrics Collection**
   - Latency calculated as (receive_time - send_time)
   - Throughput calculated as total_tasks / total_time
   - Results displayed after all tasks complete

5. **Cleanup**
   - All worker processes terminated gracefully
   - IPC socket cleaned up

## Dependencies

- Python 3.11+
- ZeroMQ (pyzmq)
- orjson (fast JSON serialization)
- pydantic (data validation)

## Configuration Constants

- `NUM_WORKERS`: 6 (number of worker processes)
- `DEFAULT_NUM_TASKS`: 50,000 (default task count)
- `MAX_IN_FLIGHT`: 24 (default max concurrent tasks)
- `IPC_PATH`: `/tmp/benchmark.ipc` (Unix domain socket path)

## Performance Characteristics

The system demonstrates excellent scalability:
- **Small batches (100 tasks)**: ~20K tasks/s with 0.4ms latency
- **Medium batches (10K tasks)**: ~30K tasks/s with 0.2ms latency
- **Large batches (1M+ tasks)**: Sustained high throughput

The max_in_flight parameter controls backpressure and prevents overwhelming workers. Lower values (like 12) provide better flow control and more predictable latency, while higher values may increase throughput at the cost of higher memory usage and latency variance.
