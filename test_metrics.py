#!/usr/bin/env python3
"""
Test script to verify VictoriaMetrics integration.
Sends a few test metrics to vmagent.
"""
import asyncio
import httpx
from push_metrics import push_worker_metrics

async def test_metrics():
    """
    Send test metrics to verify the integration works.
    """
    print("Testing VictoriaMetrics integration...")
    print(f"Endpoint: http://localhost:8429/write")
    
    async with httpx.AsyncClient() as client:
        # Send a few test metrics
        for i in range(5):
            duration_ms = 100.0 + (i * 10)
            print(f"Sending metric {i+1}/5: duration={duration_ms}ms")
            await push_worker_metrics(client, duration_ms)
            await asyncio.sleep(0.5)
    
    print("\nTest completed!")
    print("Check metrics in VictoriaMetrics UI at http://localhost:8428")
    print("Query examples:")
    print("  - worker_task_processed{lang=\"python\"}")
    print("  - worker_task_duration_ms{lang=\"python\"}")

if __name__ == "__main__":
    asyncio.run(test_metrics())