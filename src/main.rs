use anyhow::Result;
use chrono::Utc;
use clap::Parser;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;
use std::time::Instant;
use uuid::Uuid;

const IPC_PATH: &str = "ipc:///tmp/benchmark.ipc";
const IPC_FILE: &str = "/tmp/benchmark.ipc";
const NUM_WORKERS: usize = 6;
const DEFAULT_NUM_TASKS: usize = 50_000;
const MAX_IN_FLIGHT: usize = 24;

#[derive(Debug, Clone, Serialize, Deserialize)]
struct TaskData {
    id: String,
    payload: String,
    metadata: HashMap<String, String>,
    timestamp: String,
    processed: bool,
}

impl TaskData {
    fn create() -> Self {
        let payload = "x".repeat(1500);
        let mut metadata = HashMap::new();
        for i in 0..20 {
            metadata.insert(format!("key_{}", i), format!("value_{}", "y".repeat(20)));
        }

        Self {
            id: Uuid::new_v4().to_string(),
            payload,
            metadata,
            timestamp: Utc::now().to_rfc3339(),
            processed: false,
        }
    }
}

#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    /// Role to run: coordinator or worker
    #[arg(default_value = "coordinator")]
    role: String,

    /// Number of tasks to process
    #[arg(default_value_t = DEFAULT_NUM_TASKS)]
    num_tasks: usize,

    /// Maximum number of tasks in flight
    #[arg(default_value_t = MAX_IN_FLIGHT)]
    max_in_flight: usize,
}

async fn worker_async(worker_id: usize) -> Result<()> {
    let ctx = zmq::Context::new();
    let socket = ctx.socket(zmq::DEALER)?;
    
    let identity = format!("worker-{}", worker_id);
    socket.set_identity(identity.as_bytes())?;
    socket.set_linger(0)?;
    socket.connect(IPC_PATH)?;

    socket.send("READY", 0)?;

    loop {
        let mut msg = zmq::Message::new();
        match socket.recv(&mut msg, 0) {
            Ok(_) => {
                // Skip empty delimiter frame if present
                let data = if msg.is_empty() {
                    let mut data_msg = zmq::Message::new();
                    socket.recv(&mut data_msg, 0)?;
                    data_msg
                } else {
                    msg
                };

                let mut task: TaskData = serde_json::from_slice(&data)?;
                task.processed = true;
                task.timestamp = Utc::now().to_rfc3339();

                let response = serde_json::to_vec(&task)?;
                socket.send(&b""[..], zmq::SNDMORE)?;
                socket.send(&response, 0)?;
            }
            Err(_) => break,
        }
    }

    Ok(())
}

fn worker_main(worker_id: usize) {
    let rt = tokio::runtime::Runtime::new().unwrap();
    rt.block_on(async {
        if let Err(e) = worker_async(worker_id).await {
            eprintln!("Worker {} error: {}", worker_id, e);
        }
    });
}

fn master_sync(num_tasks: usize, num_workers: usize, max_in_flight: usize) -> Result<()> {
    // Clean up IPC file if it exists
    if Path::new(IPC_FILE).exists() {
        let _ = std::fs::remove_file(IPC_FILE);
    }

    let ctx = zmq::Context::new();
    let socket = ctx.socket(zmq::ROUTER)?;
    socket.set_router_mandatory(true)?;
    socket.set_linger(0)?;
    socket.set_sndhwm(2000)?;
    socket.set_rcvhwm(2000)?;
    socket.bind(IPC_PATH)?;

    let mut worker_ids: Vec<Vec<u8>> = Vec::new();
    println!("[coordinator] Waiting for {} workers...", num_workers);

    // Wait for workers to register
    while worker_ids.len() < num_workers {
        let mut ident = zmq::Message::new();
        socket.recv(&mut ident, 0)?;
        
        let mut msg = zmq::Message::new();
        socket.recv(&mut msg, 0)?;

        if msg.as_str() == Some("READY") {
            let ident_bytes = ident.to_vec();
            println!("[coordinator] Registered: {}", String::from_utf8_lossy(&ident_bytes));
            worker_ids.push(ident_bytes);
        }
    }

    println!("max in flight {}", max_in_flight);
    println!("[coordinator] Generating {} tasks...", num_tasks);
    
    let tasks: Vec<TaskData> = (0..num_tasks).map(|_| TaskData::create()).collect();
    
    let mut send_times: HashMap<String, Instant> = HashMap::new();
    let mut latencies: Vec<f64> = Vec::new();
    let start_time = Instant::now();
    
    let mut sent_count = 0;
    let mut received_count = 0;
    let mut in_flight = 0;

    // Send and receive loop
    while received_count < num_tasks {
        // Send tasks while we have capacity
        while sent_count < num_tasks && in_flight < max_in_flight {
            let task = &tasks[sent_count];
            let task_id = task.id.clone();
            let task_bytes = serde_json::to_vec(task)?;
            let ident = &worker_ids[sent_count % num_workers];
            
            let send_time = Instant::now();
            send_times.insert(task_id, send_time);
            
            socket.send(ident, zmq::SNDMORE)?;
            socket.send(&b""[..], zmq::SNDMORE)?;
            socket.send(&task_bytes, 0)?;
            
            sent_count += 1;
            in_flight += 1;
        }
        
        // Receive responses (non-blocking if we still have tasks to send)
        let flags = if sent_count < num_tasks { zmq::DONTWAIT } else { 0 };
        
        let mut ident = zmq::Message::new();
        match socket.recv(&mut ident, flags) {
            Ok(_) => {
                let mut empty = zmq::Message::new();
                socket.recv(&mut empty, 0)?;
                
                let mut data = zmq::Message::new();
                socket.recv(&mut data, 0)?;
                
                if let Ok(task) = serde_json::from_slice::<TaskData>(&data) {
                    let now = Instant::now();
                    if let Some(sent) = send_times.remove(&task.id) {
                        let latency = now.duration_since(sent).as_secs_f64() * 1000.0;
                        latencies.push(latency);
                    }
                    
                    received_count += 1;
                    in_flight -= 1;
                }
            }
            Err(zmq::Error::EAGAIN) => {
                // No message available, continue sending
                continue;
            }
            Err(e) => return Err(e.into()),
        }
    }

    let total_time = start_time.elapsed().as_secs_f64();
    let throughput = num_tasks as f64 / total_time;
    
    let avg_latency = if !latencies.is_empty() {
        latencies.iter().sum::<f64>() / latencies.len() as f64
    } else {
        0.0
    };

    println!("\n=== Results ===");
    println!("Throughput: {:.2} tasks/s", throughput);
    println!("Avg Latency: {:.3} ms", avg_latency);

    Ok(())
}

fn run_benchmark(num_tasks: usize, num_workers: usize, max_in_flight: usize) -> Result<()> {
    let mut handles = Vec::new();

    // Spawn worker processes
    for i in 0..num_workers {
        let handle = std::thread::spawn(move || {
            worker_main(i);
        });
        handles.push(handle);
    }

    // Give workers time to start
    std::thread::sleep(std::time::Duration::from_millis(500));

    // Run master
    master_sync(num_tasks, num_workers, max_in_flight)?;

    // Note: In production, you'd want proper process management
    // For now, workers will be terminated when main exits

    Ok(())
}

fn main() -> Result<()> {
    let args = Args::parse();

    if args.role == "coordinator" {
        run_benchmark(args.num_tasks, NUM_WORKERS, args.max_in_flight)?;
    } else if args.role == "worker" {
        // For manual worker mode
        worker_main(0);
    }

    Ok(())
}