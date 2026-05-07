import React, { useRef, useCallback } from "react";
import clsx from "clsx";

export interface TimelineClip {
  id: string;
  name: string;
  /** Start time in seconds */
  startTime: number;
  /** Duration in seconds */
  duration: number;
}

export interface TimelineTracks {
  video: TimelineClip[];
  audio: TimelineClip[];
  subtitles: TimelineClip[];
}

interface TimelineProps {
  tracks: TimelineTracks;
  /** Total duration in seconds */
  totalDuration: number;
  /** Current playhead position in seconds */
  currentTime: number;
  selectedClipId: string | null;
  onSelectClip: (id: string) => void;
  onScrub: (time: number) => void;
  /** Pixels per second (zoom level) */
  pixelsPerSecond?: number;
}

interface TrackRowProps {
  label: string;
  clips: TimelineClip[];
  totalDuration: number;
  pixelsPerSecond: number;
  selectedClipId: string | null;
  onSelectClip: (id: string) => void;
  clipColorClass: string;
}

function TrackRow({
  label,
  clips,
  totalDuration,
  pixelsPerSecond,
  selectedClipId,
  onSelectClip,
  clipColorClass,
}: TrackRowProps): React.ReactElement {
  const totalWidth = totalDuration * pixelsPerSecond;

  return (
    <div className="flex items-center h-8 border-b border-border">
      {/* Track label */}
      <div className="w-14 shrink-0 px-2 text-xs font-mono text-text-disabled uppercase">
        {label}
      </div>
      {/* Track content */}
      <div
        className="relative h-full bg-bg-base overflow-hidden flex-1"
        style={{ minWidth: `${totalWidth}px` }}
      >
        {clips.map((clip) => (
          <button
            key={clip.id}
            onClick={() => onSelectClip(clip.id)}
            title={clip.name}
            className={clsx(
              "absolute top-1 bottom-1 rounded text-xs font-mono px-1 truncate border transition-colors",
              clipColorClass,
              selectedClipId === clip.id
                ? "border-white opacity-100"
                : "border-transparent opacity-80 hover:opacity-100"
            )}
            style={{
              left: `${clip.startTime * pixelsPerSecond}px`,
              width: `${clip.duration * pixelsPerSecond}px`,
            }}
          >
            {clip.name}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Timeline({
  tracks,
  totalDuration,
  currentTime,
  selectedClipId,
  onSelectClip,
  onScrub,
  pixelsPerSecond = 80,
}: TimelineProps): React.ReactElement {
  const rulerRef = useRef<HTMLDivElement>(null);

  const handleRulerClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const time = Math.max(0, Math.min(x / pixelsPerSecond, totalDuration));
      onScrub(time);
    },
    [pixelsPerSecond, totalDuration, onScrub]
  );

  const totalWidth = totalDuration * pixelsPerSecond;
  const playheadLeft = currentTime * pixelsPerSecond;

  // Generate ruler ticks every second
  const ticks: number[] = [];
  for (let t = 0; t <= totalDuration; t++) {
    ticks.push(t);
  }

  return (
    <div className="flex flex-col bg-bg-surface border-t border-border overflow-x-auto">
      {/* Time ruler */}
      <div
        ref={rulerRef}
        className="relative h-6 bg-bg-elevated border-b border-border cursor-pointer select-none"
        style={{ minWidth: `${totalWidth + 56}px` }}
        onClick={handleRulerClick}
      >
        <div className="absolute left-14 top-0 h-full">
          {ticks.map((t) => (
            <div
              key={t}
              className="absolute top-0 h-full flex flex-col items-center"
              style={{ left: `${t * pixelsPerSecond}px` }}
            >
              <div className="w-px h-2 bg-border" />
              {t % 5 === 0 && (
                <span className="text-xs font-mono text-text-disabled mt-0.5 text-[10px]">
                  {t}s
                </span>
              )}
            </div>
          ))}
          {/* Playhead */}
          <div
            className="absolute top-0 h-full w-px bg-accent-primary pointer-events-none"
            style={{ left: `${playheadLeft}px` }}
          />
        </div>
      </div>

      {/* Tracks */}
      <div className="relative" style={{ minWidth: `${totalWidth + 56}px` }}>
        <TrackRow
          label="VIDEO"
          clips={tracks.video}
          totalDuration={totalDuration}
          pixelsPerSecond={pixelsPerSecond}
          selectedClipId={selectedClipId}
          onSelectClip={onSelectClip}
          clipColorClass="bg-accent-success text-bg-base"
        />
        <TrackRow
          label="AUDIO"
          clips={tracks.audio}
          totalDuration={totalDuration}
          pixelsPerSecond={pixelsPerSecond}
          selectedClipId={selectedClipId}
          onSelectClip={onSelectClip}
          clipColorClass="bg-accent-danger text-white"
        />
        <TrackRow
          label="SUBS"
          clips={tracks.subtitles}
          totalDuration={totalDuration}
          pixelsPerSecond={pixelsPerSecond}
          selectedClipId={selectedClipId}
          onSelectClip={onSelectClip}
          clipColorClass="bg-accent-info text-bg-base"
        />

        {/* Playhead line across all tracks */}
        <div
          className="absolute top-0 bottom-0 w-px bg-accent-primary pointer-events-none"
          style={{ left: `${playheadLeft + 56}px` }}
        />
      </div>
    </div>
  );
}
