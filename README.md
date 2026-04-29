# ZMQ PUSH/PULL Task Processing System

A high-performance asynchronous task processing system using ZeroMQ's PUSH/PULL pattern with a coordinator-worker architecture. Features dynamic worker scaling, language-agnostic design, and no worker registration required.

## Architecture

### PUSH/PULL Pattern

This system uses ZeroMQ's PUSH/PULL sockets for optimal load balancing and simplicity:

```
Coordinator (Rust/Python):
  ├─ PUSH socket → ipc:///tmp/benchmark-tasks.ipc (sends tasks)
  └─ PULL socket ← ipc:///tmp/benchmark-results.ipc (receives results)

Workers (Rust/Python):
  ├─ PULL socket ← receives tasks from coordinator
  └─ PUSH socket → sends results back to coordinator
```

### Key Features

- **No Registration Required**: Workers connect and start processing immediately
- **Dynamic Scaling**: Add or remove workers anytime without restarting
- **Language Agnostic**: Mix Rust and Python workers freely
- **Automatic Load Balancing**: ZMQ distributes tasks across available workers
- **Flexible Startup**: Start workers before or after coordinator
- **No Worker Count Needed**: Coordinator works with any number of workers (1, 2, 6, 100...)

### How It Works

1. **Coordinator** binds PUSH/PULL sockets and waits 2 seconds for workers
2. **Workers** connect to coordinator sockets (can connect before or after coordinator starts)
3. **Tasks** are pushed to workers via ZMQ's automatic load balancing
4. **Results** are pulled back from workers as they complete
5. **Metrics** track throughput and latency for performance analysis

## Performance Benchmarks

### Rust Coordinator + Mixed Workers (1M tasks, 24 max in-flight)

| Workers | Composition | Throughput (tasks/s) | Avg Latency (ms) |
|---------|-------------|---------------------|------------------|
| 1       | 1 Python    | 57,935              | 0.412            |
| 2       | 1 Python + 1 Rust | 103,272       | 0.230            |
| 3       | 1 Python + 2 Rust | 120,755       | 0.196            |

**Key Observations:**
- **Linear scaling**: Throughput increases proportionally with worker count
- **Sub-millisecond latency**: Consistently under 0.5ms average latency
- **Mixed workers**: Python and Rust workers work together seamlessly
- **Dynamic addition**: Workers added during runtime without restart

*Tested on Linux system with i5-12500H processor*

## Installation

### Rust Implementation

```bash
cargo build --release
```

### Python Implementation

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

## Usage

### Quick Start

**1. Start workers (any number, any order):**

```bash
# Python workers
uv run main.py worker &
uv run main.py worker &

# Rust workers
./target/release/zmq-coworkers worker &
./target/release/zmq-coworkers worker &

# Mix them!
uv run main.py worker &
./target/release/zmq-coworkers worker &
```

**2. Start coordinator:**

```bash
# Rust coordinator (recommended for performance)
./target/release/zmq-coworkers coordinator-only 1000000 24

# Python coordinator
uv run main.py coordinator 1000000 24
```

### Command Format

**Rust:**
```bash
./target/release/zmq-coworkers <role> [num_tasks] [max_in_flight]

Arguments:
  role            coordinator-only, coordinator, or worker
  num_tasks       Number of tasks to process [default: 50000]
  max_in_flight   Maximum concurrent tasks [default: 24]
```

**Python:**
```bash
uv run main.py <role> [num_tasks] [max_in_flight]

Arguments:
  role            coordinator or worker
  num_tasks       Number of tasks to process [default: 50000]
  max_in_flight   Maximum concurrent tasks [default: 24]
```

### Usage Examples

**Example 1: Start workers first**
```bash
# Terminal 1-3: Start workers
uv run main.py worker &
./target/release/zmq-coworkers worker &
./target/release/zmq-coworkers worker &

# Terminal 4: Start coordinator
./target/release/zmq-coworkers coordinator-only 1000000 24
```

**Example 2: Start coordinator first**
```bash
# Terminal 1: Start coordinator (waits for workers)
./target/release/zmq-coworkers coordinator-only 1000000 24 &

# Terminal 2-4: Start workers anytime
uv run main.py worker &
./target/release/zmq-coworkers worker &
./target/release/zmq-coworkers worker &
```

**Example 3: Add workers dynamically**
```bash
# Start with 1 worker
uv run main.py worker &
./target/release/zmq-coworkers coordinator-only 1000000 24 &

# Add more workers while running
./target/release/zmq-coworkers worker &
./target/release/zmq-coworkers worker &
```

## Task Structure

Each task contains:
- **UUID**: Unique identifier
- **Payload**: 1500 character string
- **Metadata**: 20 key-value pairs (20-char values each)
- **Timestamp**: ISO 8601 format
- **Processed flag**: Marks completion status

Example task:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "payload": "xxx...xxx",
  "metadata": {
    "key_0": "value_yyyyyyyyyyyyyyyyyyyy",
    "key_1": "value_yyyyyyyyyyyyyyyyyyyy",
    ...
  },
  "timestamp": "2024-01-15T10:30:00Z",
  "processed": false
}
```

## Architecture Details

### Coordinator Modes

**`coordinator`** (Rust/Python)
- Spawns workers internally (6 by default)
- Self-contained benchmark
- Good for quick testing

**`coordinator-only`** (Rust only)
- No internal workers
- Waits for external workers to connect
- Ideal for distributed testing and mixed-language setups

### Worker Behavior

- **Connect**: Workers connect to coordinator sockets on startup
- **Wait**: Block on PULL socket until tasks arrive
- **Process**: Receive task, mark as processed, update timestamp
- **Return**: Push result back to coordinator
- **Repeat**: Continue processing until interrupted

### Flow Control

- **Semaphore-based backpressure**: Limits concurrent in-flight tasks
- **Non-blocking receives**: Coordinator can send while waiting for results
- **Round-robin distribution**: ZMQ automatically balances load across workers

## Why PUSH/PULL?

The PUSH/PULL pattern was chosen over ROUTER/DEALER for several key advantages:

| Feature | PUSH/PULL | ROUTER/DEALER |
|---------|-----------|---------------|
| Worker Registration | ❌ Not needed | ✅ Required |
| Worker Count | ❌ Not needed | ✅ Must specify |
| Load Balancing | ✅ Automatic | ⚠️ Manual |
| Dynamic Workers | ✅ Yes | ⚠️ Limited |
| Complexity | ✅ Simple | ⚠️ Complex |
| Startup Order | ✅ Flexible | ⚠️ Coordinator first |

## Dependencies

### Rust
- `tokio` - Async runtime
- `zmq` - ZeroMQ bindings
- `serde` / `serde_json` - Serialization
- `uuid` - Unique identifiers
- `chrono` - Timestamps
- `clap` - CLI parsing
- `anyhow` - Error handling

### Python
- `pyzmq` - ZeroMQ bindings
- `orjson` - Fast JSON serialization
- `pydantic` - Data validation

## Performance Tips

1. **Use Rust coordinator** for maximum throughput
2. **Adjust max_in_flight** based on task complexity (lower for heavy tasks)
3. **Mix worker types** to utilize different CPU cores effectively
4. **Start workers first** to avoid initial connection delay
5. **Monitor latency** to find optimal worker count

## Troubleshooting

**Workers not receiving tasks:**
- Ensure coordinator started and bound sockets
- Check IPC socket paths match
- Verify no firewall blocking IPC

**Low throughput:**
- Increase `max_in_flight` parameter
- Add more workers
- Check CPU utilization

**High latency:**
- Decrease `max_in_flight` to reduce queue depth
- Reduce number of workers if CPU-bound
- Check for system resource contention

## License

MIT License - see LICENSE file for details

## Contributing

Contributions welcome! This project demonstrates:
- ZeroMQ PUSH/PULL patterns
- Mixed-language distributed systems
- High-performance async I/O
- Dynamic worker scaling