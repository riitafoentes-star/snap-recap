import React, { useState } from "react";
import { Settings } from "lucide-react";
import { MangaPageViewer, type Panel } from "../components/ingestion/MangaPageViewer";
import { ImageExplorer } from "../components/ingestion/ImageExplorer";
import { usePipelineStore } from "../store/pipelineStore";
import { runPipeline } from "../lib/ipc";

type IngestionState = "idle" | "loading" | "review" | "confirmed";

const FPS_OPTIONS = [24, 30, 60] as const;

export function IngestionScreen(): React.ReactElement {
  const { setPhase, setJobId, setJobStatus } = usePipelineStore();

  const [panels, setPanels] = useState<Panel[]>([]);
  const [selectedPanelId, setSelectedPanelId] = useState<string | null>(null);
  const [fps, setFps] = useState<24 | 30 | 60>(24);
  const [screenState, setScreenState] = useState<IngestionState>("idle");
  const [progress, setProgress] = useState(0);

  const handlePanelsAdded = (newPanels: Panel[]) => {
    setPanels((prev) => {
      const updated = [...prev, ...newPanels];
      return updated;
    });
    setScreenState("review");
  };

  const handleReorder = (reordered: Panel[]) => {
    setPanels(reordered);
  };

  const handleConfirm = async () => {
    if (panels.length === 0) return;
    setScreenState("loading");
    setProgress(0);
    setJobStatus("loading");

    try {
      const jobId = `job-${Date.now()}`;
      setJobId(jobId);

      // Simulate progress while waiting
      const interval = setInterval(() => {
        setProgress((p) => Math.min(p + 5, 90));
      }, 200);

      const result = await runPipeline({
        job_id: jobId,
        source: {
          type: "local",
          paths: panels.map((p) => p.src),
        },
        llm_provider: "openrouter",
        llm_model: "gpt-4o",
        tts_provider: "elevenlabs",
        tts_voice_id: "default",
        upscale_model: "realesrgan",
        upscale_factor: 2,
        export_format: "mp4",
        upload_youtube: false,
        output_dir: ".",
        language: "pt-BR",
      });

      clearInterval(interval);
      setProgress(100);
      setScreenState("confirmed");
      setJobStatus("running");
      setJobId(result.job_id);
      setPhase("intelligence");
    } catch (err) {
      console.error("Pipeline error:", err);
      setScreenState("review");
      setJobStatus("error");
    }
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-2 bg-bg-surface border-b border-border shrink-0">
        <h1 className="text-sm font-mono font-semibold tracking-widest text-text-primary">
          SMART_STITCH.MOD
        </h1>
        {screenState === "loading" && (
          <div className="flex-1 mx-6">
            <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
              <div
                className="h-full bg-accent-primary rounded-full transition-all duration-200"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}
        <button
          title="Settings"
          className="text-text-secondary hover:text-text-primary transition-colors"
        >
          <Settings size={16} />
        </button>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Manga Page Viewer */}
        <div className="flex flex-col w-1/2 border-r border-border overflow-hidden">
          <MangaPageViewer
            panels={panels}
            selectedPanelId={selectedPanelId}
            onPanelsAdded={handlePanelsAdded}
            onSelectPanel={setSelectedPanelId}
          />
        </div>

        {/* Right: Image Explorer */}
        <div className="flex flex-col w-1/2 overflow-hidden">
          <div className="px-3 py-2 border-b border-border shrink-0">
            <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
              Image Explorer
            </span>
          </div>
          <div className="flex-1 overflow-hidden">
            <ImageExplorer
              panels={panels}
              selectedPanelId={selectedPanelId}
              onSelectPanel={setSelectedPanelId}
              onReorder={handleReorder}
            />
          </div>
        </div>
      </div>

      {/* Bottom bar */}
      <footer className="flex items-center gap-4 px-4 py-2 bg-bg-surface border-t border-border shrink-0">
        {/* FPS selector */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-text-secondary" htmlFor="fps-select">
            FPS:
          </label>
          <select
            id="fps-select"
            value={fps}
            onChange={(e) => setFps(Number(e.target.value) as 24 | 30 | 60)}
            className="bg-bg-elevated text-text-primary text-xs rounded px-2 py-1 border border-border focus:outline-none focus:border-accent-primary"
          >
            {FPS_OPTIONS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </div>

        {/* Panel count */}
        <span className="text-xs text-text-secondary">
          Panels:{" "}
          <span className="text-text-primary font-mono">{panels.length}</span>{" "}
          detected
        </span>

        <div className="flex-1" />

        {/* Confirm button */}
        <button
          onClick={handleConfirm}
          disabled={panels.length === 0 || screenState === "loading" || screenState === "confirmed"}
          className="px-4 py-1.5 rounded bg-accent-primary text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition-opacity"
        >
          {screenState === "loading" ? "Processing…" : "Confirm"}
        </button>
      </footer>
    </div>
  );
}
