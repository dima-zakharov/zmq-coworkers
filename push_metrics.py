import httpx
import time
import asyncio

# VictoriaMetrics InfluxDB write endpoint
VM_URL = "http://localhost:8428/write"

async def push_worker_metrics(client, worker_id, task_duration_ms):
    # Measurement: task_processed
    # Tags: worker_id, lang
    # Field: duration
    line = f"task_processed,worker_id={worker_id},lang=python duration={task_duration_ms}"
    try:
        # Short timeout to prevent blocking the main loop
        await client.post(VM_URL, content=line, timeout=0.1)
    except Exception:
        # Silently ignore errors to keep the worker running
        pass

# Usage inside your worker loop:
# start = time.perf_counter()
# ... process task ...
# end = time.perf_counter()
# await push_worker_metrics(client, "py_worker_1", (end - start) * 1000)