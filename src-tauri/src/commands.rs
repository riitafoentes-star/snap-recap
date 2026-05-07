use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::HashMap;
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_shell::ShellExt;

/// Global state to track running sidecar processes
pub struct SidecarState {
    processes: HashMap<String, tauri_plugin_shell::process::CommandChild>,
}

impl SidecarState {
    pub fn new() -> Self {
        Self {
            processes: HashMap::new(),
        }
    }
}

/// Configuration for a pipeline job, mirroring the Python PipelineConfig model.
#[derive(Debug, Deserialize, Serialize)]
pub struct PipelineConfig {
    pub job_id: String,
    pub source: serde_json::Value,
    pub llm_provider: String,
    pub llm_model: String,
    pub tts_provider: String,
    pub tts_voice_id: String,
    pub upscale_model: String,
    pub upscale_factor: u32,
    pub export_format: String,
    pub upload_youtube: bool,
    pub output_dir: String,
    pub language: String,
}

/// Result returned by the pipeline after execution.
#[derive(Debug, Serialize, Deserialize)]
pub struct JobResult {
    pub job_id: String,
    pub status: String,
    pub output_files: Vec<String>,
    pub youtube_url: Option<String>,
    pub duration_seconds: f64,
    pub error: Option<String>,
}

/// Status of a pipeline job.
#[derive(Debug, Serialize)]
pub struct JobStatus {
    pub job_id: String,
    pub status: String,
    pub current_phase: Option<String>,
    pub progress: f64,
}

/// Invoke the Python sidecar to run the full pipeline.
///
/// # Arguments
/// * `app` - The Tauri app handle for spawning the sidecar and emitting events.
/// * `config` - The pipeline configuration.
///
/// # Returns
/// A `JobResult` with the outcome of the pipeline execution.
#[tauri::command]
pub async fn run_pipeline(
    app: AppHandle,
    config: PipelineConfig,
) -> Result<JobResult, String> {
    let job_id = config.job_id.clone();
    
    // Spawn the Python sidecar
    let sidecar_command = app
        .shell()
        .sidecar("snap-recap-pipeline")
        .map_err(|e| format!("Failed to create sidecar command: {}", e))?;
    
    let (mut rx, mut child) = sidecar_command
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {}", e))?;
    
    // Store the child process in global state
    let state = app.state::<Mutex<SidecarState>>();
    {
        let mut state_guard = state.lock().unwrap();
        state_guard.processes.insert(job_id.clone(), child);
    }
    
    // Send the run_pipeline command via stdin
    let command = json!({
        "method": "run_pipeline",
        "params": {
            "config": config
        }
    });
    
    let command_str = format!("{}\n", serde_json::to_string(&command).unwrap());
    
    // Get the child process back to write to stdin
    let state = app.state::<Mutex<SidecarState>>();
    let mut state_guard = state.lock().unwrap();
    if let Some(child) = state_guard.processes.get_mut(&job_id) {
        child
            .write(command_str.as_bytes())
            .map_err(|e| format!("Failed to write to sidecar stdin: {}", e))?;
    }
    drop(state_guard);
    
    // Listen for stdout events in a background task
    let app_clone = app.clone();
    let job_id_clone = job_id.clone();
    tauri::async_runtime::spawn(async move {
        let mut final_result: Option<JobResult> = None;
        
        while let Some(event) = rx.recv().await {
            match event {
                tauri_plugin_shell::process::CommandEvent::Stdout(line) => {
                    // Convert Vec<u8> to String
                    if let Ok(line_str) = String::from_utf8(line) {
                        // Parse the JSON event from Python
                        if let Ok(event_data) = serde_json::from_str::<serde_json::Value>(&line_str) {
                            if let Some(event_name) = event_data.get("event").and_then(|v| v.as_str()) {
                                let data = event_data.get("data").cloned().unwrap_or(json!({}));
                                
                                // Emit the event to the frontend
                                let _ = app_clone.emit(event_name, data.clone());
                                
                                // If this is the done event, store the result
                                if event_name == "pipeline:done" {
                                    if let Ok(result) = serde_json::from_value::<JobResult>(data) {
                                        final_result = Some(result);
                                    }
                                }
                            }
                        }
                    }
                }
                tauri_plugin_shell::process::CommandEvent::Stderr(line) => {
                    if let Ok(line_str) = String::from_utf8(line) {
                        eprintln!("[sidecar stderr] {}", line_str);
                    }
                }
                tauri_plugin_shell::process::CommandEvent::Error(err) => {
                    eprintln!("[sidecar error] {}", err);
                    let _ = app_clone.emit("pipeline:error", json!({
                        "message": format!("Sidecar error: {}", err)
                    }));
                }
                tauri_plugin_shell::process::CommandEvent::Terminated(payload) => {
                    eprintln!("[sidecar terminated] code: {:?}", payload.code);
                    
                    // Remove from state
                    let state = app_clone.state::<Mutex<SidecarState>>();
                    let mut state_guard = state.lock().unwrap();
                    state_guard.processes.remove(&job_id_clone);
                    
                    break;
                }
                _ => {}
            }
        }
    });
    
    // Return a pending result immediately (the actual result will come via events)
    Ok(JobResult {
        job_id: config.job_id,
        status: "RUNNING".to_string(),
        output_files: vec![],
        youtube_url: None,
        duration_seconds: 0.0,
        error: None,
    })
}

/// Send a cancellation signal to a running pipeline job.
///
/// # Arguments
/// * `app` - The Tauri app handle.
/// * `job_id` - The ID of the job to cancel.
#[tauri::command]
pub async fn cancel_job(app: AppHandle, job_id: String) -> Result<(), String> {
    // Send cancel command to the sidecar
    let command = json!({
        "method": "cancel_job",
        "params": {
            "job_id": job_id
        }
    });
    
    let command_str = format!("{}\n", serde_json::to_string(&command).unwrap());
    
    let state = app.state::<Mutex<SidecarState>>();
    let mut state_guard = state.lock().unwrap();
    
    if let Some(child) = state_guard.processes.get_mut(&job_id) {
        child
            .write(command_str.as_bytes())
            .map_err(|e| format!("Failed to write cancel command: {}", e))?;
        Ok(())
    } else {
        Err(format!("No running job found with id: {}", job_id))
    }
}

/// Query the current status of a pipeline job.
///
/// # Arguments
/// * `job_id` - The ID of the job to query.
///
/// # Returns
/// A `JobStatus` with the current state of the job.
#[tauri::command]
pub async fn get_job_status(app: AppHandle, job_id: String) -> Result<JobStatus, String> {
    let state = app.state::<Mutex<SidecarState>>();
    let state_guard = state.lock().unwrap();
    
    let status = if state_guard.processes.contains_key(&job_id) {
        "RUNNING"
    } else {
        "UNKNOWN"
    };
    
    Ok(JobStatus {
        job_id,
        status: status.to_string(),
        current_phase: None,
        progress: 0.0,
    })
}
