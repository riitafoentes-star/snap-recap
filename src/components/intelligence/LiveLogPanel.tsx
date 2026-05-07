import React, { useEffect, useRef, useState } from "react";
import { onPipelineLog } from "../../lib/ipc";

interface LiveLogPanelProps {
  /** Additional log lines to display (e.g. from parent state) */
  extraLines?: string[];
}

export function LiveLogPanel({ extraLines = [] }: LiveLogPanelProps): React.ReactElement {
  const [lines, setLines] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Subscribe to pipeline:log events
  useEffect(() => {
    let unlisten: (() => void) | null = null;

    onPipelineLog((message) => {
      setLines((prev) => [...prev, message]);
    }).then((fn) => {
      unlisten = fn;
    });

    return () => {
      unlisten?.();
    };
  }, []);

  // Auto-scroll to bottom on new lines
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines, extraLines]);

  const allLines = [...lines, ...extraLines];

  return (
    <div className="flex flex-col h-full bg-bg-base rounded-lg border border-border overflow-hidden">
      <div className="flex items-center px-3 py-1.5 border-b border-border bg-bg-surface shrink-0">
        <span className="text-xs font-mono text-text-secondary uppercase tracking-wider">
          Live Log
        </span>
        <div className="ml-2 flex gap-1">
          <span className="w-2 h-2 rounded-full bg-accent-danger" />
          <span className="w-2 h-2 rounded-full bg-accent-primary opacity-50" />
          <span className="w-2 h-2 rounded-full bg-accent-success opacity-50" />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-3 font-mono text-xs text-text-secondary leading-relaxed">
        {allLines.length === 0 ? (
          <span className="text-text-disabled">Waiting for pipeline output…</span>
        ) : (
          allLines.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap break-all">
              <span className="text-text-disabled select-none mr-2">
                {String(i + 1).padStart(4, "0")}
              </span>
              {line}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
