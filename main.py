#!/usr/bin/env python3
import argparse
import asyncio
import multiprocessing as mp
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import orjson
import zmq
import zmq.asyncio
from pydantic import BaseModel, Field, ConfigDict

IPC_PATH = "ipc:///tmp/benchmark.ipc"
IPC_FILE = Path("/tmp/benchmark.ipc")
NUM_WORKERS = 6
DEFAULT_NUM_TASKS = 50_000
MAX_IN_FLIGHT = 24


class TaskData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: uuid.UUID
    payload: str
    metadata: dict[str, Any]
    timestamp: datetime
    processed: bool = Field(default=False)

def create_task() -> dict:
    payload = "x" * 1500
    metadata = {f"key_{i}": "value_" + ("y" * 20) for i in range(20)}
    return {
        "id": str(uuid.uuid4()),
        "payload": payload,
        "metadata": metadata,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "processed": False,
    }

# --- WORKER LOGIC ---

async def worker_async(worker_id: int) -> None:
    ctx = zmq.asyncio.Context.instance()
    socket = ctx.socket(zmq.DEALER)
    socket.setsockopt(zmq.IDENTITY, f"worker-{worker_id}".encode())
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect(IPC_PATH)

    await socket.send(b"READY")

    while True:
        try:
            frames = await socket.recv_multipart()
            data = frames[1]
            
            obj = orjson.loads(data)
            obj["processed"] = True
            obj["timestamp"] = datetime.now(timezone.utc).isoformat()

            await socket.send_multipart([b"", orjson.dumps(obj)])
        except Exception:
            break

def worker_main(worker_id: int) -> None:
    asyncio.run(worker_async(worker_id))

# --- MASTER LOGIC ---

async def master_async(num_tasks: int, num_workers: int) -> None:
    if IPC_FILE.exists():
        try:
            IPC_FILE.unlink()
        except OSError:
            pass

    ctx = zmq.asyncio.Context.instance()
    socket = ctx.socket(zmq.ROUTER)
    socket.setsockopt(zmq.ROUTER_MANDATORY, 1)
    socket.setsockopt(zmq.LINGER, 0)
    socket.setsockopt(zmq.SNDHWM, 2000) 
    socket.bind(IPC_PATH)

    worker_ids: list[bytes] = []
    print(f"[coordinator] Waiting for {num_workers} workers...")

    while len(worker_ids) < num_workers:
        ident, msg = await socket.recv_multipart()
        if msg == b"READY":
            worker_ids.append(ident)
            print(f"[coordinator] Registered: {ident.decode()}")

    sem = asyncio.Semaphore(MAX_IN_FLIGHT)
    
    print ("max in flight", MAX_IN_FLIGHT)
    print(f"[coordinator] Generating {num_tasks} tasks...")
    tasks = [create_task() for _ in range(num_tasks)]
    
    send_times: dict[str, float] = {}
    latencies: list[float] = []
    start_time = time.perf_counter()
    received_count = 0

    async def sender():
        for i in range(num_tasks):
            await sem.acquire()
            
            task = tasks[i]
            task_id = task["id"]
            task_bytes = orjson.dumps(task)
            
            send_times[task_id] = time.perf_counter()
            ident = worker_ids[i % num_workers]
            
            try:
                await socket.send_multipart([ident, b"", task_bytes])
            except Exception as e:
                print(f"Send error: {e}")
                sem.release()

    async def receiver():
        nonlocal received_count
        while received_count < num_tasks:
            ident, empty, data = await socket.recv_multipart()
            
            sem.release()
            
            obj = orjson.loads(data)
            task_id = obj["id"]
            
            sent = send_times.pop(task_id, None)
            if sent:
                latencies.append(time.perf_counter() - sent)
            
            received_count += 1

    await asyncio.gather(sender(), receiver())

    total_time = time.perf_counter() - start_time
    throughput = num_tasks / total_time
    avg_latency = (sum(latencies) / len(latencies)) * 1000 if latencies else 0

    print(f"\n=== Results ===")
    print(f"Throughput: {throughput:,.2f} tasks/s")
    print(f"Avg Latency: {avg_latency:.3f} ms")

def run_benchmark(num_tasks: int, num_workers: int) -> None:
    procs = []
    ctx = mp.get_context("spawn")

    for i in range(num_workers):
        p = ctx.Process(target=worker_main, args=(i,))
        p.start()
        procs.append(p)

    try:
        asyncio.run(master_async(num_tasks, num_workers))
    finally:
        for p in procs:
            p.terminate()
            p.join()

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["coordinator", "worker"], default="coordinator", nargs="?")
    parser.add_argument("num_tasks", type=int, default=DEFAULT_NUM_TASKS, nargs="?")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    if args.role == "coordinator":
        run_benchmark(args.num_tasks, NUM_WORKERS)