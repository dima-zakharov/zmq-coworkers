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

IPC_PATH_TASKS = "ipc:///tmp/benchmark-tasks.ipc"
IPC_PATH_RESULTS = "ipc:///tmp/benchmark-results.ipc"
IPC_FILE = Path("/tmp/benchmark.ipc")
NUM_WORKERS = 6
DEFAULT_NUM_TASKS = 50_000
MAX_IN_FLIGHT = 24


class TaskData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: uuid.UUID
    payload: str
    metadata:[str, Any]
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
    
    # PULL socket to receive tasks
    pull_socket = ctx.socket(zmq.PULL)
    pull_socket.connect(IPC_PATH_TASKS)
    
    # PUSH socket to send results
    push_socket = ctx.socket(zmq.PUSH)
    push_socket.connect(IPC_PATH_RESULTS)
    
    print(f"[worker-{worker_id}] Connected and ready")

    while True:
        try:
            data = await pull_socket.recv()
            
            obj = orjson.loads(data)
            obj["processed"] = True
            obj["timestamp"] = datetime.now(timezone.utc).isoformat()

            await push_socket.send(orjson.dumps(obj))
        except Exception as e:
            print(f"[worker-{worker_id}] Error: {e}")
            break

def worker_main(worker_id: int) -> None:
    asyncio.run(worker_async(worker_id))

# --- MASTER LOGIC ---

async def master_async(num_tasks: int, num_workers: int, max_in_flight: int) -> None:
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
    socket.bind("ipc:///tmp/benchmark.ipc")

    worker_ids: list[bytes] = []
    print(f"[coordinator] Waiting for {num_workers} workers...")

    while len(worker_ids) < num_workers:
        ident, msg = await socket.recv_multipart()
        if msg == b"READY":
            worker_ids.append(ident)
            print(f"[coordinator] Registered: {ident.decode()}")

    sem = asyncio.Semaphore(max_in_flight)
    
    print ("max in flight", max_in_flight)
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

def run_benchmark(num_tasks: int, num_workers: int, max_in_flight: int) -> None:
    procs = []
    ctx = mp.get_context("spawn")

    for i in range(num_workers):
        p = ctx.Process(target=worker_main, args=(i,))
        p.start()
        procs.append(p)

    try:
        asyncio.run(master_async(num_tasks, num_workers, max_in_flight))
    finally:
        for p in procs:
            p.terminate()
            p.join()

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["coordinator", "worker"], default="coordinator", nargs="?")
    parser.add_argument("num_tasks", type=int, default=DEFAULT_NUM_TASKS, nargs="?")
    parser.add_argument("max_in_flight", type=int, default=MAX_IN_FLIGHT, nargs="?")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    if args.role == "coordinator":
        run_benchmark(args.num_tasks, NUM_WORKERS, args.max_in_flight)
    elif args.role == "worker":
        worker_id = 0
        worker_main(worker_id)