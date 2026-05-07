/**
 * Snap Recap — Global pipeline state (Zustand store stub).
 *
 * Full implementation in Task 23.3.
 */

import { create } from "zustand";
import type { JobResult } from "../lib/ipc";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type Phase = "ingestion" | "intelligence" | "production";

export type JobStatus = "idle" | "loading" | "running" | "done" | "error";

export interface ProgressMap {
  scriptGeneration: number;
  voiceSynthesis: number;
  imageUpscale: number;
}

// ---------------------------------------------------------------------------
// Store shape
// ---------------------------------------------------------------------------

interface PipelineState {
  /** Currently active navigation phase. */
  currentPhase: Phase;
  /** ID of the active pipeline job, if any. */
  jobId: string | null;
  /** High-level job status. */
  jobStatus: JobStatus;
  /** Per-task progress percentages (0–100). */
  progressMap: ProgressMap;
  /** Final job result once the pipeline completes. */
  jobResult: JobResult | null;

  // Actions
  setPhase: (phase: Phase) => void;
  setJobId: (jobId: string | null) => void;
  setJobStatus: (status: JobStatus) => void;
  updateProgress: (task: keyof ProgressMap, percent: number) => void;
  setJobResult: (result: JobResult | null) => void;
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

const initialState: Omit<
  PipelineState,
  | "setPhase"
  | "setJobId"
  | "setJobStatus"
  | "updateProgress"
  | "setJobResult"
  | "reset"
> = {
  currentPhase: "ingestion",
  jobId: null,
  jobStatus: "idle",
  progressMap: {
    scriptGeneration: 0,
    voiceSynthesis: 0,
    imageUpscale: 0,
  },
  jobResult: null,
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const usePipelineStore = create<PipelineState>((set) => ({
  ...initialState,

  setPhase: (phase) => set({ currentPhase: phase }),

  setJobId: (jobId) => set({ jobId }),

  setJobStatus: (status) => set({ jobStatus: status }),

  updateProgress: (task, percent) =>
    set((state) => ({
      progressMap: { ...state.progressMap, [task]: percent },
    })),

  setJobResult: (result) => set({ jobResult: result }),

  reset: () => set(initialState),
}));
