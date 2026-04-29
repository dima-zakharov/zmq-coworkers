#!/usr/bin/env python3
"""
Test script to verify VictoriaMetrics integration with batching.
Sends test metrics to vmagent in batches.
"""
import asyncio
import httpx
from push_metrics import push_worker_metrics_batch

async def test_metrics():
    """
    Send test metrics to verify the batching integration works.
    """
    print("Testing VictoriaMetrics batched integration...")
    print(f"Endpoint: http://localhost:8429/write")
    
    async with httpx.AsyncClient() as client:
        # Test 1: Small batch
        print("\n[Test 1] Sending small batch (5 metrics)...")
        small_batch = [100.0 + (i * 10) for i in range(5)]
        await push_worker_metrics_batch(client, small_batch)
        print(f"Sent {len(small_batch)} metrics")
        await asyncio.sleep(1)
        
        # Test 2: Large batch (simulating high throughput)
        print("\n[Test 2] Sending large batch (1000 metrics)...")
        large_batch = [50.0 + (i * 0.1) for i in range(1000)]
        await push_worker_metrics_batch(client, large_batch)
        print(f"Sent {len(large_batch)} metrics")
        await asyncio.sleep(1)
        
        # Test 3: Multiple batches
        print("\n[Test 3] Sending multiple batches (3 x 100 metrics)...")
        for batch_num in range(3):
            batch = [75.0 + (i * 0.5) for i in range(100)]
            await push_worker_metrics_batch(client, batch)
            print(f"Sent batch {batch_num + 1}: {len(batch)} metrics")
            await asyncio.sleep(0.5)
    
    print("\n✅ Test completed!")
    print("Check metrics in VictoriaMetrics UI at http://localhost:8428")
    print("\nQuery examples:")
    print("  - sum(worker_task_processed{lang=\"python\"})")
    print("  - avg(worker_task_duration_ms{lang=\"python\"})")
    print("  - rate(worker_task_processed{lang=\"python\"}[1m])")

if __name__ == "__main__":
    asyncio.run(test_metrics())
