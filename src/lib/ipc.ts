/**
 * Snap Recap — Tauri IPC helpers.
 *
 * Typed wrappers around Tauri Commands and event listeners.
 */

import { invoke } from "@tauri-apps/api/core";
import { listen, UnlistenFn } from "@tauri-apps/api/event";

// ---------------------------------------------------------------------------
// Types mirroring Python models
// ---------------------------------------------------------------------------

export interface PipelineConfig {
  job_id: string;
  source: PageSource;
  llm_provider: string;
  llm_model: string;
  tts_provider: string;
  tts_voice_id: string;
  upscale_model: string;
  upscale_factor: number;
  export_format: "mp4" | "otioz" | "both";
  upload_youtube: boolean;
  output_dir: string;
  language: string;
}

export type PageSource =
  | { type: "mangadex"; chapter_id: string }
  | { type: "local"; paths: string[] };

export interface JobResult {
  job_id: string;
  status: "SUCCESS" | "FAILED" | "PARTIAL" | "RUNNING";
  output_files: string[];
  youtube_url: string | null;
  duration_seconds: number;
  error: string | null;
}

export interface JobStatus {
  job_id: string;
  status: string;
  current_phase: string | null;
  progress: number;
}

export interface ProgressEvent {
  phase: string;
  percent: number;
  message: string;
}

export interface LogEvent {
  message: string;
}

export interface ErrorEvent {
  message: string;
}

// ---------------------------------------------------------------------------
// Command wrappers
// ---------------------------------------------------------------------------

/** Invoke the Python sidecar to run the full pipeline. */
export async function runPipeline(config: PipelineConfig): Promise<JobResult> {
  return invoke<JobResult>("run_pipeline", { config });
}

/** Send a cancellation signal to a running job. */
export async function cancelJob(jobId: string): Promise<void> {
  return invoke<void>("cancel_job", { jobId });
}

/** Query the current status of a pipeline job. */
export async function getJobStatus(jobId: string): Promise<JobStatus> {
  return invoke<JobStatus>("get_job_status", { jobId });
}

// ---------------------------------------------------------------------------
// Event listeners
// ---------------------------------------------------------------------------

/** Subscribe to pipeline progress events. Returns an unsubscribe function. */
export async function onPipelineProgress(
  handler: (event: ProgressEvent) => void
): Promise<UnlistenFn> {
  return listen<ProgressEvent>("pipeline:progress", (e) => handler(e.payload));
}

/** Subscribe to pipeline log events. Returns an unsubscribe function. */
export async function onPipelineLog(
  handler: (message: string) => void
): Promise<UnlistenFn> {
  return listen<LogEvent>("pipeline:log", (e) => handler(e.payload.message));
}

/** Subscribe to pipeline error events. Returns an unsubscribe function. */
export async function onPipelineError(
  handler: (message: string) => void
): Promise<UnlistenFn> {
  return listen<ErrorEvent>("pipeline:error", (e) =>
    handler(e.payload.message)
  );
}

/** Subscribe to the pipeline completion event. Returns an unsubscribe function. */
export async function onPipelineDone(
  handler: (result: JobResult) => void
): Promise<UnlistenFn> {
  return listen<JobResult>("pipeline:done", (e) => handler(e.payload));
}
