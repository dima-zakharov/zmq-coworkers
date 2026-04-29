#!/usr/bin/env python3
import argparse
import asyncio
import multiprocessing as mp
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import orjson
import zmq
import zmq.asyncio
from pydantic import BaseModel, Field

IPC_PATH = "ipc:///tmp/benchmark.ipc"
IPC_FILE = Path("/tmp/benchmark.ipc")
NUM_WORKERS = 6
DEFAULT_NUM_TASKS = 50_000


class TaskData(BaseModel):
    id: uuid.UUID
    payload: str
    metadata: Dict[str, Any]
    timestamp: datetime
    processed: bool = Field(default=False)

    class Config:
        arbitrary_types_allowed = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ZeroMQ coordinator/worker benchmark")
    parser.add_argument(
        "role",
        choices=["coordinator", "worker"],
        help="Run as coordinator or worker",
    )
    parser.add_argument(
        "num_tasks",
        nargs="?",
        type=int,
        default=DEFAULT_NUM_TASKS,
        help=f"Number of tasks for coordinator (default: {DEFAULT_NUM_TASKS})",
    )
    parser.add_argument(
        "--worker-id",
        type=int,
        default=0,
        help="Worker identifier when running in worker mode",
    )
    return parser.parse_args()


def make_task_payload() -> Tuple[str, Dict[str, Any]]:
    payload = "x" * 1500
    metadata = {f"key_{i}": "value_" + ("y" * 20) for i in range(20)}
    return payload, metadata


PAYLOAD_TEMPLATE, METADATA_TEMPLATE = make_task_payload()


def create_task() -> TaskData:
    return TaskData(
        id=uuid.uuid4(),
        payload=PAYLOAD_TEMPLATE,
        metadata=METADATA_TEMPLATE,
        timestamp=datetime.now(timezone.utc),
        processed=False,
    )


async def worker_async(worker_id: int) -> None:
    ctx = zmq.asyncio.Context.instance()
    socket = ctx.socket(zmq.DEALER)
    socket.setsockopt(zmq.IDENTITY, f"worker-{worker_id}".encode())
    socket.connect(IPC_PATH)

    await socket.send(b"READY")

    while True:
        frames = await socket.recv_multipart()
        if len(frames) != 2:
            continue

        _, data = frames
        obj = orjson.loads(data)
        task = TaskData.model_validate(obj)
        task.processed = True
        task.timestamp = datetime.now(timezone.utc)

        out_bytes = orjson.dumps(task.model_dump(mode="json"))
        await socket.send_multipart([b"", out_bytes])


def worker_main(worker_id: int) -> None:
    asyncio.run(worker_async(worker_id))


async def master_async(num_tasks: int, num_workers: int) -> None:
    if IPC_FILE.exists():
        try:
            IPC_FILE.unlink()
        except OSError:
            pass

    ctx = zmq.asyncio.Context.instance()
    socket = ctx.socket(zmq.ROUTER)
    socket.bind(IPC_PATH)

    worker_ids: List[bytes] = []
    print(f"[coordinator] Waiting for {num_workers} workers to register...")

    while len(worker_ids) < num_workers:
        frames = await socket.recv_multipart()
        if len(frames) != 2:
            continue

        ident, msg = frames
        if msg == b"READY":
            worker_ids.append(ident)
            print(f"[coordinator] Worker registered: {ident.decode(errors='replace')}")

    print(f"[coordinator] All workers registered, starting benchmark with {num_tasks} tasks")

    send_times: Dict[uuid.UUID, float] = {}
    latencies: List[float] = []

    start_time = time.perf_counter()

    for i in range(num_tasks):
        task = create_task()
        task_bytes = orjson.dumps(task.model_dump(mode="json"))
        send_times[task.id] = time.perf_counter()
        ident = worker_ids[i % num_workers]
        await socket.send_multipart([ident, b"", task_bytes])

    received = 0
    while received < num_tasks:
        frames = await socket.recv_multipart()
        if len(frames) != 3:
            continue

        ident, empty, data = frames
        _ = ident, empty

        obj = orjson.loads(data)
        task = TaskData.model_validate(obj)
        sent = send_times.pop(task.id, None)
        if sent is None:
            continue

        latencies.append(time.perf_counter() - sent)
        received += 1

    total_time = time.perf_counter() - start_time
    throughput = num_tasks / total_time if total_time > 0 else float("inf")
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

    print("\n=== Benchmark Results ===")
    print(f"Tasks processed: {num_tasks}")
    print(f"Workers: {num_workers}")
    print(f"Total time: {total_time:.6f} s")
    print(f"Throughput: {throughput:,.2f} tasks/s")
    print(f"Average latency: {avg_latency * 1000:.3f} ms")


def run_benchmark(num_tasks: int = DEFAULT_NUM_TASKS, num_workers: int = NUM_WORKERS) -> None:
    procs: List[mp.Process] = []
    ctx = mp.get_context("spawn")

    for i in range(num_workers):
        proc = ctx.Process(target=worker_main, args=(i,))
        proc.start()
        procs.append(proc)

    try:
        asyncio.run(master_async(num_tasks, num_workers))
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            proc.join()


if __name__ == "__main__":
    os.environ["PYTHONASYNCIODEBUG"] = "0"

    args = parse_args()

    if args.role == "coordinator":
        print(f"--- Starting COORDINATOR (Expects {NUM_WORKERS} workers) ---")
        run_benchmark(args.num_tasks, NUM_WORKERS)
    elif args.role == "worker":
        print(f"--- Starting WORKER (PID: {os.getpid()}) ---")
        asyncio.run(worker_async(worker_id=args.worker_id))
