import React, { useState } from "react";
import { X, CheckCircle2, ExternalLink } from "lucide-react";
import clsx from "clsx";

export type ExportFormat = "mp4" | "otioz" | "both";

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onExport: (format: ExportFormat, uploadYouTube: boolean) => void;
  /** 0–100, null when not exporting */
  exportProgress: number | null;
  /** Set when export is complete */
  exportedFilePath: string | null;
  youtubeUrl: string | null;
}

export function ExportModal({
  isOpen,
  onClose,
  onExport,
  exportProgress,
  exportedFilePath,
  youtubeUrl,
}: ExportModalProps): React.ReactElement | null {
  const [format, setFormat] = useState<ExportFormat>("mp4");
  const [uploadYouTube, setUploadYouTube] = useState(false);

  if (!isOpen) return null;

  const isExporting = exportProgress !== null && exportProgress < 100;
  const isDone = exportedFilePath !== null;

  const handleExport = () => {
    onExport(format, uploadYouTube);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-60">
      <div className="bg-bg-surface border border-border rounded-xl w-96 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="text-sm font-semibold text-text-primary">Export</h2>
          <button
            onClick={onClose}
            className="text-text-secondary hover:text-text-primary transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="p-4 flex flex-col gap-4">
          {isDone ? (
            /* Success state */
            <div className="flex flex-col items-center gap-3 py-4">
              <CheckCircle2 size={40} className="text-accent-success" />
              <p className="text-sm text-text-primary font-semibold">Export complete!</p>
              {exportedFilePath && (
                <p className="text-xs text-text-secondary font-mono break-all text-center">
                  {exportedFilePath}
                </p>
              )}
              {youtubeUrl && (
                <a
                  href={youtubeUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-accent-info hover:underline"
                >
                  <ExternalLink size={12} />
                  View on YouTube
                </a>
              )}
            </div>
          ) : (
            <>
              {/* Format selection */}
              <div className="flex flex-col gap-2">
                <label className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                  Format
                </label>
                <div className="flex gap-2">
                  {(["mp4", "otioz", "both"] as ExportFormat[]).map((f) => (
                    <button
                      key={f}
                      onClick={() => setFormat(f)}
                      className={clsx(
                        "flex-1 py-1.5 rounded text-xs font-mono border transition-colors",
                        format === f
                          ? "bg-accent-primary border-accent-primary text-white"
                          : "border-border text-text-secondary hover:border-text-secondary"
                      )}
                    >
                      {f === "both" ? "MP4 + OTIOZ" : f.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>

              {/* YouTube toggle */}
              <label className="flex items-center gap-3 cursor-pointer">
                <div className="relative">
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={uploadYouTube}
                    onChange={(e) => setUploadYouTube(e.target.checked)}
                  />
                  <div
                    className={clsx(
                      "w-9 h-5 rounded-full transition-colors",
                      uploadYouTube ? "bg-accent-primary" : "bg-bg-elevated"
                    )}
                  />
                  <div
                    className={clsx(
                      "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform",
                      uploadYouTube && "translate-x-4"
                    )}
                  />
                </div>
                <span className="text-sm text-text-secondary">Upload to YouTube</span>
              </label>

              {/* FFmpeg progress bar */}
              {isExporting && (
                <div className="flex flex-col gap-1">
                  <div className="flex justify-between text-xs text-text-secondary">
                    <span>Exporting…</span>
                    <span className="font-mono">{exportProgress}%</span>
                  </div>
                  <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                    <div
                      className="h-full bg-accent-primary rounded-full transition-all duration-200"
                      style={{ width: `${exportProgress}%` }}
                    />
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        {!isDone && (
          <div className="flex justify-end gap-2 px-4 py-3 border-t border-border">
            <button
              onClick={onClose}
              disabled={isExporting}
              className="px-3 py-1.5 rounded text-sm text-text-secondary hover:text-text-primary border border-border hover:border-text-secondary transition-colors disabled:opacity-40"
            >
              Cancel
            </button>
            <button
              onClick={handleExport}
              disabled={isExporting}
              className="px-4 py-1.5 rounded bg-accent-primary text-white text-sm font-semibold disabled:opacity-40 hover:opacity-90 transition-opacity"
            >
              {isExporting ? "Exporting…" : "Export"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
