import React from "react";
import { Grid, Cpu, Film, Settings } from "lucide-react";
import { usePipelineStore, type Phase } from "../store/pipelineStore";
import clsx from "clsx";

interface NavItem {
  phase: Phase;
  icon: React.ReactNode;
  label: string;
}

const NAV_ITEMS: NavItem[] = [
  { phase: "ingestion", icon: <Grid size={20} />, label: "Ingestion" },
  { phase: "intelligence", icon: <Cpu size={20} />, label: "Intelligence" },
  { phase: "production", icon: <Film size={20} />, label: "Production" },
];

export function NavigationSidebar(): React.ReactElement {
  const { currentPhase, setPhase, jobStatus } = usePipelineStore();

  // Intelligence and Production are disabled until a job has been started
  const isPhaseEnabled = (phase: Phase): boolean => {
    if (phase === "ingestion") return true;
    if (phase === "intelligence") return jobStatus !== "idle";
    if (phase === "production") return jobStatus === "done";
    return false;
  };

  return (
    <aside className="flex flex-col items-center w-14 bg-bg-surface border-r border-border py-4 gap-2 shrink-0">
      {NAV_ITEMS.map(({ phase, icon, label }) => {
        const enabled = isPhaseEnabled(phase);
        const active = currentPhase === phase;

        return (
          <button
            key={phase}
            title={label}
            disabled={!enabled}
            onClick={() => enabled && setPhase(phase)}
            className={clsx(
              "flex items-center justify-center w-10 h-10 rounded-lg transition-colors",
              active && "text-accent-primary bg-bg-elevated",
              !active && enabled && "text-text-secondary hover:text-text-primary hover:bg-bg-elevated",
              !enabled && "text-text-disabled cursor-not-allowed"
            )}
          >
            {icon}
          </button>
        );
      })}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Settings button */}
      <button
        title="Settings"
        className="flex items-center justify-center w-10 h-10 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors"
      >
        <Settings size={20} />
      </button>
    </aside>
  );
}
