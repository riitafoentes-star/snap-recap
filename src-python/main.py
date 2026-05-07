"""
Snap Recap — Python sidecar entry point.

Receives JSON-RPC commands from the Tauri shell via stdin and emits
progress events via stdout. Dispatches to PipelineOrchestrator.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path
from typing import Dict, Optional

from models import PipelineConfig, JobResult
from pipeline.orchestrator import PipelineOrchestrator

# Configure logging to stderr so it doesn't interfere with stdout events
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Global orchestrator instance
_orchestrator: Optional[PipelineOrchestrator] = None
# Map from job_id to running thread
_running_jobs: Dict[str, threading.Thread] = {}


def main() -> None:
    """Read JSON-RPC commands from stdin and dispatch to the pipeline."""
    global _orchestrator
    
    # Initialize orchestrator with progress callback
    _orchestrator = PipelineOrchestrator(on_progress=_on_progress)
    
    _emit_log("Python sidecar started, waiting for commands...")
    
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            command = json.loads(line)
            _dispatch(command)
        except json.JSONDecodeError as exc:
            _emit_error(f"Invalid JSON: {exc}")
        except Exception as exc:
            logger.exception("Unexpected error in main loop: %s", exc)
            _emit_error(f"Unexpected error: {exc}")


def _dispatch(command: dict) -> None:
    """Dispatch a parsed command to the appropriate handler."""
    method = command.get("method", "")
    params = command.get("params", {})

    if method == "run_pipeline":
        _handle_run_pipeline(params)
    elif method == "resume_job":
        _handle_resume_job(params)
    elif method == "cancel_job":
        _handle_cancel_job(params)
    else:
        _emit_error(f"Unknown method: {method}")


def _handle_run_pipeline(params: dict) -> None:
    """Handle run_pipeline command by spawning a background thread."""
    try:
        # Parse config from params
        config_dict = params.get("config", {})
        if not config_dict:
            _emit_error("Missing 'config' in run_pipeline params")
            return
        
        # Convert output_dir to Path
        if "output_dir" in config_dict:
            config_dict["output_dir"] = Path(config_dict["output_dir"])
        
        config = PipelineConfig(**config_dict)
        job_id = config.job_id
        
        # Check if job is already running
        if job_id in _running_jobs and _running_jobs[job_id].is_alive():
            _emit_error(f"Job {job_id} is already running")
            return
        
        _emit_log(f"Starting pipeline for job {job_id}")
        
        # Run pipeline in background thread
        thread = threading.Thread(
            target=_run_pipeline_thread,
            args=(config,),
            daemon=True,
            name=f"pipeline-{job_id}",
        )
        _running_jobs[job_id] = thread
        thread.start()
        
    except Exception as exc:
        logger.exception("Error in _handle_run_pipeline: %s", exc)
        _emit_error(f"Failed to start pipeline: {exc}")


def _handle_resume_job(params: dict) -> None:
    """Handle resume_job command by spawning a background thread."""
    try:
        job_id = params.get("job_id")
        if not job_id:
            _emit_error("Missing 'job_id' in resume_job params")
            return
        
        # Check if job is already running
        if job_id in _running_jobs and _running_jobs[job_id].is_alive():
            _emit_error(f"Job {job_id} is already running")
            return
        
        _emit_log(f"Resuming job {job_id}")
        
        # Run resume in background thread
        thread = threading.Thread(
            target=_resume_job_thread,
            args=(job_id,),
            daemon=True,
            name=f"resume-{job_id}",
        )
        _running_jobs[job_id] = thread
        thread.start()
        
    except Exception as exc:
        logger.exception("Error in _handle_resume_job: %s", exc)
        _emit_error(f"Failed to resume job: {exc}")


def _handle_cancel_job(params: dict) -> None:
    """Handle cancel_job command by signaling the orchestrator."""
    try:
        job_id = params.get("job_id")
        if not job_id:
            _emit_error("Missing 'job_id' in cancel_job params")
            return
        
        _emit_log(f"Cancelling job {job_id}")
        
        if _orchestrator:
            _orchestrator.cancel_job(job_id)
            _emit_log(f"Cancellation signal sent for job {job_id}")
        else:
            _emit_error("Orchestrator not initialized")
            
    except Exception as exc:
        logger.exception("Error in _handle_cancel_job: %s", exc)
        _emit_error(f"Failed to cancel job: {exc}")


def _run_pipeline_thread(config: PipelineConfig) -> None:
    """Run the pipeline in a background thread and emit the result."""
    try:
        result = _orchestrator.run_pipeline(config)
        _emit_done(result)
    except Exception as exc:
        logger.exception("Pipeline execution failed: %s", exc)
        _emit_error(f"Pipeline execution failed: {exc}")


def _resume_job_thread(job_id: str) -> None:
    """Resume a job in a background thread and emit the result."""
    try:
        result = _orchestrator.resume_job(job_id)
        _emit_done(result)
    except Exception as exc:
        logger.exception("Job resume failed: %s", exc)
        _emit_error(f"Job resume failed: {exc}")


def _on_progress(phase: str, percent: float, message: str) -> None:
    """Progress callback invoked by the orchestrator."""
    _emit("pipeline:progress", {
        "phase": phase,
        "percent": percent,
        "message": message,
    })


def _emit(event: str, data: dict) -> None:
    """Write a JSON event to stdout for the Tauri shell to consume."""
    payload = json.dumps({"event": event, "data": data})
    print(payload, flush=True)


def _emit_log(message: str) -> None:
    """Emit a log event."""
    _emit("pipeline:log", {"message": message})


def _emit_error(message: str) -> None:
    """Emit an error event."""
    _emit("pipeline:error", {"message": message})


def _emit_done(result: JobResult) -> None:
    """Emit a pipeline completion event."""
    # Convert JobResult to dict for JSON serialization
    result_dict = {
        "job_id": result.job_id,
        "status": result.status.value,
        "output_files": [str(p) for p in result.output_files],
        "youtube_url": result.youtube_url,
        "duration_seconds": result.duration_seconds,
        "error": result.error,
    }
    _emit("pipeline:done", result_dict)


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
