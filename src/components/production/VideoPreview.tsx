import React from "react";
import { SkipBack, SkipForward, Play, Pause, ChevronLeft, ChevronRight } from "lucide-react";

interface VideoPreviewProps {
  /** Current playhead position in seconds */
  currentTime: number;
  /** Total duration in seconds */
  duration: number;
  isPlaying: boolean;
  onPlay: () => void;
  onPause: () => void;
  onStepBack: () => void;
  onStepForward: () => void;
  onSkipToStart: () => void;
  onSkipToEnd: () => void;
  fps?: number;
}

/** Format seconds to HH:MM:SS:FF timecode */
function toTimecode(seconds: number, fps = 24): string {
  const totalFrames = Math.floor(seconds * fps);
  const frames = totalFrames % fps;
  const totalSecs = Math.floor(seconds);
  const secs = totalSecs % 60;
  const mins = Math.floor(totalSecs / 60) % 60;
  const hours = Math.floor(totalSecs / 3600);
  return [
    String(hours).padStart(2, "0"),
    String(mins).padStart(2, "0"),
    String(secs).padStart(2, "0"),
    String(frames).padStart(2, "0"),
  ].join(":");
}

export function VideoPreview({
  currentTime,
  duration,
  isPlaying,
  onPlay,
  onPause,
  onStepBack,
  onStepForward,
  onSkipToStart,
  onSkipToEnd,
  fps = 24,
}: VideoPreviewProps): React.ReactElement {
  return (
    <div className="flex flex-col flex-1 bg-bg-base overflow-hidden">
      {/* Preview area */}
      <div className="flex-1 flex items-center justify-center bg-black relative overflow-hidden">
        {/* Placeholder frame */}
        <div className="flex flex-col items-center gap-2 text-text-disabled">
          <div className="w-24 h-16 rounded border border-border flex items-center justify-center">
            <span className="text-xs font-mono">PREVIEW</span>
          </div>
          <span className="text-xs">Anime / Manga frame</span>
        </div>
        {/* Timecode overlay */}
        <div className="absolute bottom-2 right-3 font-mono text-xs text-text-secondary bg-bg-base bg-opacity-70 px-2 py-0.5 rounded">
          {toTimecode(currentTime, fps)}
        </div>
      </div>

      {/* Playback controls */}
      <div className="flex items-center justify-center gap-2 py-2 bg-bg-surface border-t border-border shrink-0">
        <button
          onClick={onSkipToStart}
          title="Skip to start"
          className="text-text-secondary hover:text-text-primary transition-colors p-1"
        >
          <SkipBack size={16} />
        </button>
        <button
          onClick={onStepBack}
          title="Step back"
          className="text-text-secondary hover:text-text-primary transition-colors p-1"
        >
          <ChevronLeft size={16} />
        </button>
        <button
          onClick={isPlaying ? onPause : onPlay}
          title={isPlaying ? "Pause" : "Play"}
          className="text-text-primary hover:text-accent-primary transition-colors p-1"
        >
          {isPlaying ? <Pause size={20} /> : <Play size={20} />}
        </button>
        <button
          onClick={onStepForward}
          title="Step forward"
          className="text-text-secondary hover:text-text-primary transition-colors p-1"
        >
          <ChevronRight size={16} />
        </button>
        <button
          onClick={onSkipToEnd}
          title="Skip to end"
          className="text-text-secondary hover:text-text-primary transition-colors p-1"
        >
          <SkipForward size={16} />
        </button>
        <span className="ml-3 font-mono text-xs text-text-secondary">
          {toTimecode(currentTime, fps)} / {toTimecode(duration, fps)}
        </span>
      </div>
    </div>
  );
}
