import React from "react";
import { Film } from "lucide-react";
import clsx from "clsx";

export interface Clip {
  id: string;
  name: string;
  /** Duration in seconds */
  duration: number;
  /** Optional thumbnail URL */
  thumbnail?: string;
}

interface AssetPanelProps {
  clips: Clip[];
  selectedClipId: string | null;
  onSelectClip: (id: string) => void;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function AssetPanel({
  clips,
  selectedClipId,
  onSelectClip,
}: AssetPanelProps): React.ReactElement {
  return (
    <div className="flex flex-col h-full bg-bg-surface border-r border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border shrink-0">
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          Clips / Assets
        </span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {clips.length === 0 ? (
          <div className="flex items-center justify-center h-full text-text-disabled text-xs">
            No clips
          </div>
        ) : (
          clips.map((clip) => (
            <button
              key={clip.id}
              onClick={() => onSelectClip(clip.id)}
              className={clsx(
                "flex items-center gap-2 w-full px-3 py-2 text-left transition-colors border-b border-border",
                selectedClipId === clip.id
                  ? "bg-bg-elevated text-text-primary"
                  : "hover:bg-bg-elevated text-text-secondary"
              )}
            >
              {/* Thumbnail */}
              <div className="w-10 h-7 rounded bg-bg-base flex items-center justify-center shrink-0 overflow-hidden">
                {clip.thumbnail ? (
                  <img
                    src={clip.thumbnail}
                    alt={clip.name}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <Film size={14} className="text-text-disabled" />
                )}
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-xs font-medium truncate">{clip.name}</span>
                <span className="text-xs text-text-disabled font-mono">
                  {formatDuration(clip.duration)}
                </span>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
