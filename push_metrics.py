import httpx
import time
import asyncio
import socket

# VictoriaMetrics vmagent InfluxDB write endpoint
VM_URL = "http://localhost:8429/write"

# Get worker ID from hostname
WORKER_ID = socket.gethostname()

async def push_worker_metrics(client: httpx.AsyncClient, task_duration_ms: float):
    """
    Push worker metrics to VictoriaMetrics using InfluxDB Line Protocol.
    
    Metrics sent:
    - worker_task_processed: Counter incremented for each completed task
    - worker_task_duration_ms: Gauge recording task processing time
    
    Tags:
    - worker_id: Unique identifier (hostname)
    - lang: Language identifier (python)
    
    Args:
        client: httpx AsyncClient instance
        task_duration_ms: Task duration in milliseconds
    """
    timestamp_ns = int(time.time() * 1_000_000_000)
    
    # Build InfluxDB Line Protocol messages
    # Format: measurement,tag1=value1,tag2=value2 field1=value1,field2=value2 timestamp
    lines = [
        f"worker_task_processed,worker_id={WORKER_ID},lang=python count=1 {timestamp_ns}",
        f"worker_task_duration_ms,worker_id={WORKER_ID},lang=python value={task_duration_ms} {timestamp_ns}"
    ]
    
    payload = "\n".join(lines)
    
    try:
        # Fire-and-forget with very short timeout (50ms)
        await client.post(
            VM_URL,
            content=payload,
            timeout=0.05,
            headers={"Content-Type": "text/plain"}
        )
    except Exception:
        # Silently ignore errors to keep the worker running
        pass
