import React, { useState, useEffect, useRef } from "react";
import { Settings } from "lucide-react";
import { AssetPanel, type Clip } from "../components/production/AssetPanel";
import { VideoPreview } from "../components/production/VideoPreview";
import { Timeline, type TimelineTracks } from "../components/production/Timeline";
import { ExportModal, type ExportFormat } from "../components/production/ExportModal";
import { usePipelineStore } from "../store/pipelineStore";
import { runPipeline } from "../lib/ipc";

type ProductionState = "loading" | "ready" | "exporting" | "exported";

// ---------------------------------------------------------------------------
// Demo data — replaced by real pipeline output in production
// ---------------------------------------------------------------------------

const DEMO_CLIPS: Clip[] = [
  { id: "clip_001", name: "clip_001", duration: 5.5 },
  { id: "clip_002", name: "clip_002", duration: 4.2 },
  { id: "clip_003", name: "clip_003", duration: 6.0 },
  { id: "narr_001", name: "narr_001", duration: 5.5 },
  { id: "narr_002", name: "narr_002", duration: 4.2 },
];

const DEMO_TRACKS: TimelineTracks = {
  video: [
    { id: "clip_001", name: "clip_001", startTime: 0, duration: 5.5 },
    { id: "clip_002", name: "clip_002", startTime: 5.5, duration: 4.2 },
    { id: "clip_003", name: "clip_003", startTime: 9.7, duration: 6.0 },
  ],
  audio: [
    { id: "narr_001", name: "narr_001", startTime: 0, duration: 5.5 },
    { id: "narr_002", name: "narr_002", startTime: 5.5, duration: 4.2 },
  ],
  subtitles: [
    { id: "sub_001", name: "sub_001", startTime: 0.5, duration: 4.5 },
    { id: "sub_002", name: "sub_002", startTime: 6.0, duration: 3.5 },
  ],
};

const TOTAL_DURATION = 15.7;

export function ProductionScreen(): React.ReactElement {
  const { jobId, setJobStatus } = usePipelineStore();

  const [screenState, setScreenState] = useState<ProductionState>("loading");
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportProgress, setExportProgress] = useState<number | null>(null);
  const [exportedFilePath, setExportedFilePath] = useState<string | null>(null);
  const [youtubeUrl, setYoutubeUrl] = useState<string | null>(null);

  const playIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Simulate loading state on mount
  useEffect(() => {
    const timer = setTimeout(() => setScreenState("ready"), 800);
    return () => clearTimeout(timer);
  }, []);

  // Playback interval
  useEffect(() => {
    if (isPlaying) {
      playIntervalRef.current = setInterval(() => {
        setCurrentTime((t) => {
          if (t >= TOTAL_DURATION) {
            setIsPlaying(false);
            return TOTAL_DURATION;
          }
          return t + 1 / 24;
        });
      }, 1000 / 24);
    } else {
      if (playIntervalRef.current) {
        clearInterval(playIntervalRef.current);
        playIntervalRef.current = null;
      }
    }
    return () => {
      if (playIntervalRef.current) clearInterval(playIntervalRef.current);
    };
  }, [isPlaying]);

  const handleSelectClip = (id: string) => {
    setSelectedClipId(id);
    // Move playhead to clip start
    const allClips = [
      ...DEMO_TRACKS.video,
      ...DEMO_TRACKS.audio,
      ...DEMO_TRACKS.subtitles,
    ];
    const clip = allClips.find((c) => c.id === id);
    if (clip) setCurrentTime(clip.startTime);
  };

  const handleExport = async (format: ExportFormat, uploadYouTube: boolean) => {
    if (!jobId) return;
    setScreenState("exporting");
    setExportProgress(0);

    try {
      // Simulate FFmpeg progress
      const interval = setInterval(() => {
        setExportProgress((p) => {
          if (p === null || p >= 95) return p;
          return p + 5;
        });
      }, 300);

      const result = await runPipeline({
        job_id: jobId,
        source: { type: "local", paths: [] },
        llm_provider: "openrouter",
        llm_model: "gpt-4o",
        tts_provider: "elevenlabs",
        tts_voice_id: "default",
        upscale_model: "realesrgan",
        upscale_factor: 2,
        export_format: format,
        upload_youtube: uploadYouTube,
        output_dir: ".",
        language: "pt-BR",
      });

      clearInterval(interval);
      setExportProgress(100);
      setScreenState("exported");
      setJobStatus("done");
      setExportedFilePath(result.output_files[0] ?? "output.mp4");
      setYoutubeUrl(result.youtube_url);
    } catch (err) {
      console.error("Export error:", err);
      setExportProgress(null);
      setScreenState("ready");
    }
  };

  if (screenState === "loading") {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
          <span className="text-text-secondary text-sm">Loading timeline…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-2 bg-bg-surface border-b border-border shrink-0">
        <h1 className="text-sm font-mono font-semibold tracking-widest text-text-primary">
          TIMELINE_EDITOR
        </h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowExportModal(true)}
            disabled={screenState === "exporting"}
            className="flex items-center gap-1.5 px-3 py-1 rounded bg-accent-primary text-white text-xs font-semibold hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            EXPORT .OTIOZ
          </button>
          <button
            title="Settings"
            className="text-text-secondary hover:text-text-primary transition-colors"
          >
            <Settings size={16} />
          </button>
        </div>
      </header>

      {/* Main content: AssetPanel + VideoPreview */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: Asset panel */}
        <div className="w-44 shrink-0 overflow-hidden">
          <AssetPanel
            clips={DEMO_CLIPS}
            selectedClipId={selectedClipId}
            onSelectClip={handleSelectClip}
          />
        </div>

        {/* Right: Video preview */}
        <VideoPreview
          currentTime={currentTime}
          duration={TOTAL_DURATION}
          isPlaying={isPlaying}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onStepBack={() => setCurrentTime((t) => Math.max(0, t - 1 / 24))}
          onStepForward={() =>
            setCurrentTime((t) => Math.min(TOTAL_DURATION, t + 1 / 24))
          }
          onSkipToStart={() => setCurrentTime(0)}
          onSkipToEnd={() => setCurrentTime(TOTAL_DURATION)}
          fps={24}
        />
      </div>

      {/* Timeline */}
      <div className="shrink-0 overflow-x-auto">
        <Timeline
          tracks={DEMO_TRACKS}
          totalDuration={TOTAL_DURATION}
          currentTime={currentTime}
          selectedClipId={selectedClipId}
          onSelectClip={handleSelectClip}
          onScrub={setCurrentTime}
          pixelsPerSecond={80}
        />
      </div>

      {/* Export modal */}
      <ExportModal
        isOpen={showExportModal}
        onClose={() => setShowExportModal(false)}
        onExport={handleExport}
        exportProgress={exportProgress}
        exportedFilePath={exportedFilePath}
        youtubeUrl={youtubeUrl}
      />
    </div>
  );
}
