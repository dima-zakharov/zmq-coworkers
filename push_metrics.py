import httpx 

async def push_worker_metrics_batch(client: httpx.AsyncClient, durations_ms: list[float]):
    if not durations_ms:
        return
        
        lines = []
        for duration_ms in durations_ms:
            lines.append(f"worker_task_processed,worker_id={WORKER_ID},lang=python count=1")
            lines.append(f"worker_task_duration_ms,worker_id={WORKER_ID},lang=python value={duration_ms}")
            
            payload = "\n".join(lines)
            
            try:
                await client.post(
                    "http://localhost:8089/write", 
                    content=payload,
                    timeout=0.5,
                    headers={"Content-Type": "text/plain"}
                    )
            except Exception as e:
                print(f"Metrics error: {e}")
                pass