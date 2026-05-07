import React from "react";
import { Loader2, CheckCircle2, XCircle, Clock } from "lucide-react";
import clsx from "clsx";

export type TaskStatus = "pending" | "running" | "done" | "error";

export interface PhaseTask {
  id: string;
  task: string;
  percent: number;
  provider: string;
  status: TaskStatus;
}

interface PhaseProgressListProps {
  tasks: PhaseTask[];
}

function StatusIcon({ status }: { status: TaskStatus }): React.ReactElement {
  switch (status) {
    case "running":
      return <Loader2 size={16} className="text-accent-primary animate-spin" />;
    case "done":
      return <CheckCircle2 size={16} className="text-accent-success" />;
    case "error":
      return <XCircle size={16} className="text-accent-danger" />;
    default:
      return <Clock size={16} className="text-text-disabled" />;
  }
}

export function PhaseProgressList({
  tasks,
}: PhaseProgressListProps): React.ReactElement {
  return (
    <div className="flex flex-col gap-4">
      {tasks.map((t) => (
        <div key={t.id} className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <StatusIcon status={t.status} />
              <span className="text-sm text-text-primary">{t.task}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-text-secondary">{t.provider}</span>
              <span
                className={clsx(
                  "text-xs font-mono",
                  t.status === "done"
                    ? "text-accent-success"
                    : t.status === "error"
                    ? "text-accent-danger"
                    : "text-text-secondary"
                )}
              >
                {t.percent}%
              </span>
            </div>
          </div>
          {/* Progress bar */}
          <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
            <div
              className={clsx(
                "h-full rounded-full transition-all duration-300",
                t.status === "done"
                  ? "bg-accent-success"
                  : t.status === "error"
                  ? "bg-accent-danger"
                  : "bg-accent-primary"
              )}
              style={{ width: `${t.percent}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
