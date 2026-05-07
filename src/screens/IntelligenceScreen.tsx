import React, { useEffect, useState } from "react";
import { PhaseProgressList, type PhaseTask } from "../components/intelligence/PhaseProgressList";
import { LiveLogPanel } from "../components/intelligence/LiveLogPanel";
import { usePipelineStore } from "../store/pipelineStore";
import { cancelJob, onPipelineProgress, onPipelineDone, onPipelineError } from "../lib/ipc";

const INITIAL_TASKS: PhaseTask[] = [
  {
    id: "scriptGeneration",
    task: "Script Generation",
    percent: 0,
    provider: "OpenRouter",
    status: "pending",
  },
  {
    id: "voiceSynthesis",
    task: "Voice Synthesis",
    percent: 0,
    provider: "ElevenLabs",
    status: "pending",
  },
  {
    id: "imageUpscale",
    task: "Image Upscale",
    percent: 0,
    provider: "Real-ESRGAN",
    status: "pending",
  },
];

export function IntelligenceScreen(): React.ReactElement {
  const { jobId, jobStatus, setPhase, setJobStatus, updateProgress, progressMap } =
    usePipelineStore();

  const [tasks, setTasks] = useState<PhaseTask[]>(INITIAL_TASKS);
  const [logLines, setLogLines] = useState<string[]>([]);

  const allDone = tasks.every((t) => t.status === "done" || t.status === "error");
  const isRunning = jobStatus === "running" || jobStatus === "loading";

  // Sync tasks with progressMap from store
  useEffect(() => {
    setTasks((prev) =>
      prev.map((t) => {
        const key = t.id as keyof typeof progressMap;
        const percent = progressMap[key] ?? t.percent;
        let status = t.status;
        if (percent > 0 && percent < 100 && status === "pending") status = "running";
        if (percent >= 100) status = "done";
        return { ...t, percent, status };
      })
    );
  }, [progressMap]);

  // Subscribe to pipeline events
  useEffect(() => {
    const unlisteners: Array<() => void> = [];

    onPipelineProgress((event) => {
      const phaseMap: Record<string, keyof typeof progressMap> = {
        script_generation: "scriptGeneration",
        voice_synthesis: "voiceSynthesis",
        image_upscale: "imageUpscale",
      };
      const key = phaseMap[event.phase];
      if (key) {
        updateProgress(key, event.percent);
      }
      setLogLines((prev) => [...prev, `[${event.phase}] ${event.message}`]);
    }).then((fn) => unlisteners.push(fn));

    onPipelineDone((result) => {
      setJobStatus("done");
      setLogLines((prev) => [
        ...prev,
        `Pipeline done — status: ${result.status}`,
      ]);
      // Mark all tasks as done
      setTasks((prev) => prev.map((t) => ({ ...t, percent: 100, status: "done" })));
    }).then((fn) => unlisteners.push(fn));

    onPipelineError((message) => {
      setJobStatus("error");
      setLogLines((prev) => [...prev, `ERROR: ${message}`]);
      setTasks((prev) =>
        prev.map((t) =>
          t.status === "running" ? { ...t, status: "error" } : t
        )
      );
    }).then((fn) => unlisteners.push(fn));

    return () => {
      unlisteners.forEach((fn) => fn());
    };
  }, [updateProgress, setJobStatus]);

  const handleCancel = async () => {
    if (!jobId) return;
    try {
      await cancelJob(jobId);
      setJobStatus("idle");
    } catch (err) {
      console.error("Cancel error:", err);
    }
  };

  const handleContinue = () => {
    setPhase("production");
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-2 bg-bg-surface border-b border-border shrink-0">
        <h1 className="text-sm font-mono font-semibold tracking-widest text-text-primary">
          INTELLIGENCE
        </h1>
        <span className="text-xs text-text-secondary">
          {isRunning ? "Processing…" : allDone ? "Complete" : "Waiting"}
        </span>
      </header>

      {/* Content */}
      <div className="flex flex-col flex-1 overflow-hidden p-4 gap-4">
        {/* Phase progress */}
        <div className="bg-bg-surface rounded-lg border border-border p-4 shrink-0">
          <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-4">
            Pipeline Tasks
          </h2>
          <PhaseProgressList tasks={tasks} />
        </div>

        {/* Live log */}
        <div className="flex-1 overflow-hidden">
          <LiveLogPanel extraLines={logLines} />
        </div>
      </div>

      {/* Footer actions */}
      <footer className="flex items-center justify-end gap-3 px-4 py-2 bg-bg-surface border-t border-border shrink-0">
        {isRunning && (
          <button
            onClick={handleCancel}
            className="px-4 py-1.5 rounded border border-accent-danger text-accent-danger text-sm hover:bg-accent-danger hover:text-white transition-colors"
          >
            Cancel
          </button>
        )}
        <button
          onClick={handleContinue}
          disabled={!allDone}
          className="px-4 py-1.5 rounded bg-accent-primary text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition-opacity"
        >
          Continue to Production
        </button>
      </footer>
    </div>
  );
}
