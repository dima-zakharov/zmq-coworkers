#!/usr/bin/env python3
import asyncio
import httpx
import traceback
import time

# IMPORTANT: send directly to VictoriaMetrics, not vmagent
URL = "http://127.0.0.1:8428/write"

async def push_metrics(client, values):
    """
    Send a batch of metrics to VictoriaMetrics using Influx line protocol.
    Each metric is given a unique timestamp to prevent deduplication.
    """
    base_ts_ms = int(time.time() * 1000)

    lines = []
    for i, v in enumerate(values):
        # Subtract 100ms per value so they are clearly separated on a graph
        ts = base_ts_ms - (i * 100) 
        # VictoriaMetrics Influx parser will auto-detect ms if the number is the right length,
        # but it's safer to tell your ingestion tool the precision is 'ms'
        lines.append(f"worker_task_processed,lang=python value={v} {ts}")
    payload = "\n".join(lines) + "\n"

    try:
        response = await client.post(
            URL,
            content=payload,
            headers={"Content-Type": "text/plain"},
        )

        print(f"➡️  Sent {len(values)} metrics")
        print(f"   Status: {response.status_code}")

        if response.status_code not in (200, 204):
            print("❌ Unexpected response:", response.text)

    except Exception:
        print("❌ Error sending metrics:")
        traceback.print_exc()

async def main():
    print(f"🚀 Testing VictoriaMetrics ingestion at {URL}\n")

    async with httpx.AsyncClient(timeout=10.0) as client:
        print("[Test 1] Small batch...")
        await push_metrics(client, [1.1, 2.2, 3.3])

        await asyncio.sleep(0.5)

        print("\n[Test 2] Large batch...")
        await push_metrics(client, [100*float(i) for i in range(100)])

if __name__ == "__main__":
    asyncio.run(main())