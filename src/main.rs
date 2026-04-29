use anyhow::Result;
use chrono::Utc;
use clap::Parser;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::Instant;
use uuid::Uuid;

const IPC_PATH_TASKS: &str = "ipc:///tmp/benchmark-tasks.ipc";
const IPC_PATH_RESULTS: &str = "ipc:///tmp/benchmark-results.ipc";
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
    /// Role to run: coordinator, coordinator-only, or worker
    #[arg(default_value = "coordinator")]
    role: String,

    /// Number of tasks to process
    #[arg(default_value_t = DEFAULT_NUM_TASKS)]
    num_tasks: usize,

    /// Maximum number of tasks in flight
    #[arg(default_value_t = MAX_IN_FLIGHT)]
    max_in_flight: usize,
}

fn worker_main(worker_id: usize) -> Result<()> {
    let ctx = zmq::Context::new();
    
    // PULL socket to receive tasks
    let pull_socket = ctx.socket(zmq::PULL)?;
    pull_socket.connect(IPC_PATH_TASKS)?;
    
    // PUSH socket to send results
    let push_socket = ctx.socket(zmq::PUSH)?;
    push_socket.connect(IPC_PATH_RESULTS)?;
    
    println!("[worker-{}] Connected and ready", worker_id);

    loop {
        let mut msg = zmq::Message::new();
        match pull_socket.recv(&mut msg, 0) {
            Ok(_) => {
                let mut task: TaskData = serde_json::from_slice(&msg)?;
                task.processed = true;
                task.timestamp = Utc::now().to_rfc3339();

                let response = serde_json::to_vec(&task)?;
                push_socket.send(&response, 0)?;
            }
            Err(e) => {
                eprintln!("[worker-{}] Error: {}", worker_id, e);
                break;
            }
        }
    }

    Ok(())
}

fn coordinator_main(num_tasks: usize, max_in_flight: usize) -> Result<()> {
    // Clean up IPC files
    let _ = std::fs::remove_file("/tmp/benchmark-tasks.ipc");
    let _ = std::fs::remove_file("/tmp/benchmark-results.ipc");

    let ctx = zmq::Context::new();
    
    // PUSH socket to send tasks to workers
    let push_socket = ctx.socket(zmq::PUSH)?;
    push_socket.set_sndhwm(2000)?;
    push_socket.bind(IPC_PATH_TASKS)?;
    
    // PULL socket to receive results from workers
    let pull_socket = ctx.socket(zmq::PULL)?;
    pull_socket.set_rcvhwm(2000)?;
    pull_socket.bind(IPC_PATH_RESULTS)?;
    
    println!("[coordinator] Sockets ready. Waiting 2 seconds for workers to connect...");
    std::thread::sleep(std::time::Duration::from_secs(2));

    println!("max in flight {}", max_in_flight);
    println!("[coordinator] Generating {} tasks...", num_tasks);
    println!("[coordinator] Workers can connect anytime - tasks will be distributed automatically");
    
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
            
            let send_time = Instant::now();
            send_times.insert(task_id, send_time);
            
            push_socket.send(&task_bytes, 0)?;
            
            sent_count += 1;
            in_flight += 1;
        }
        
        // Receive responses (non-blocking if we still have tasks to send)
        let flags = if sent_count < num_tasks { zmq::DONTWAIT } else { 0 };
        
        let mut data = zmq::Message::new();
        match pull_socket.recv(&mut data, flags) {
            Ok(_) => {
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

fn main() -> Result<()> {
    let args = Args::parse();

    match args.role.as_str() {
        "coordinator" | "coordinator-only" => {
            coordinator_main(args.num_tasks, args.max_in_flight)?;
        }
        "worker" => {
            worker_main(0)?;
        }
        _ => {
            eprintln!("Unknown role: {}", args.role);
            std::process::exit(1);
        }
    }

    Ok(())
}
