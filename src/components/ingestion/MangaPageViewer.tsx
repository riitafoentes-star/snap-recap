import React, { useCallback, useState } from "react";
import { Upload } from "lucide-react";
import clsx from "clsx";

export interface Panel {
  id: string;
  /** Object URL for the uploaded image */
  src: string;
  /** Display label */
  label: string;
}

interface MangaPageViewerProps {
  panels: Panel[];
  selectedPanelId: string | null;
  onPanelsAdded: (panels: Panel[]) => void;
  onSelectPanel: (id: string) => void;
}

export function MangaPageViewer({
  panels,
  selectedPanelId,
  onPanelsAdded,
  onSelectPanel,
}: MangaPageViewerProps): React.ReactElement {
  const [draggingOver, setDraggingOver] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDraggingOver(false);
      const files = Array.from(e.dataTransfer.files).filter((f) =>
        f.type.startsWith("image/")
      );
      if (files.length === 0) return;

      const newPanels: Panel[] = files.map((file, i) => ({
        id: `panel-${Date.now()}-${i}`,
        src: URL.createObjectURL(file),
        label: file.name,
      }));
      onPanelsAdded(newPanels);
    },
    [onPanelsAdded]
  );

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDraggingOver(true);
  };

  const handleDragLeave = () => setDraggingOver(false);

  return (
    <div
      className="flex flex-col h-full overflow-y-auto bg-bg-base"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
    >
      {panels.length === 0 ? (
        /* Idle: drag-drop zone */
        <div
          className={clsx(
            "flex flex-col items-center justify-center flex-1 m-4 rounded-xl border-2 border-dashed transition-colors",
            draggingOver
              ? "border-accent-primary bg-bg-elevated"
              : "border-border"
          )}
        >
          <Upload size={40} className="text-text-disabled mb-3" />
          <p className="text-text-secondary text-sm">
            Drop manga pages here
          </p>
          <p className="text-text-disabled text-xs mt-1">
            PNG, JPG, WEBP supported
          </p>
        </div>
      ) : (
        /* Review: pages stacked vertically */
        <div className="flex flex-col gap-2 p-4">
          {panels.map((panel) => (
            <div
              key={panel.id}
              onClick={() => onSelectPanel(panel.id)}
              className={clsx(
                "relative rounded-lg overflow-hidden cursor-pointer border-2 transition-colors",
                selectedPanelId === panel.id
                  ? "border-accent-primary"
                  : "border-transparent hover:border-border"
              )}
            >
              <img
                src={panel.src}
                alt={panel.label}
                className="w-full object-contain"
              />
              {/* Colored overlay for selected panel */}
              {selectedPanelId === panel.id && (
                <div className="absolute inset-0 bg-accent-primary opacity-20 pointer-events-none" />
              )}
              <span className="absolute bottom-1 left-1 text-xs bg-bg-base bg-opacity-70 text-text-secondary px-1 rounded">
                {panel.label}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
