import React from "react";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  useSortable,
  rectSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import clsx from "clsx";
import type { Panel } from "./MangaPageViewer";

// Palette for placeholder colors when no real image is available
const PLACEHOLDER_COLORS = [
  "bg-accent-primary",
  "bg-accent-success",
  "bg-accent-danger",
  "bg-accent-info",
];

interface SortableCardProps {
  panel: Panel;
  index: number;
  isSelected: boolean;
  onSelect: (id: string) => void;
}

function SortableCard({
  panel,
  index,
  isSelected,
  onSelect,
}: SortableCardProps): React.ReactElement {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: panel.id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const colorClass = PLACEHOLDER_COLORS[index % PLACEHOLDER_COLORS.length];

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={() => onSelect(panel.id)}
      className={clsx(
        "relative rounded-lg overflow-hidden cursor-pointer border-2 transition-colors select-none",
        isSelected ? "border-accent-primary" : "border-transparent hover:border-border"
      )}
    >
      {/* 16:9 aspect ratio container */}
      <div className="aspect-video w-full relative">
        {panel.src ? (
          <img
            src={panel.src}
            alt={panel.label}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className={clsx("w-full h-full", colorClass)} />
        )}
        {/* Panel index badge */}
        <span className="absolute top-1 left-1 text-xs bg-bg-base bg-opacity-80 text-text-primary px-1.5 py-0.5 rounded font-mono">
          {index + 1}
        </span>
      </div>
      <p className="text-xs text-text-secondary truncate px-1 py-0.5 bg-bg-surface">
        {panel.label}
      </p>
    </div>
  );
}

interface ImageExplorerProps {
  panels: Panel[];
  selectedPanelId: string | null;
  onSelectPanel: (id: string) => void;
  onReorder: (panels: Panel[]) => void;
}

export function ImageExplorer({
  panels,
  selectedPanelId,
  onSelectPanel,
  onReorder,
}: ImageExplorerProps): React.ReactElement {
  const sensors = useSensors(useSensor(PointerSensor));

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over && active.id !== over.id) {
      const oldIndex = panels.findIndex((p) => p.id === active.id);
      const newIndex = panels.findIndex((p) => p.id === over.id);
      onReorder(arrayMove(panels, oldIndex, newIndex));
    }
  };

  if (panels.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-text-disabled text-sm">
        No panels yet
      </div>
    );
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={handleDragEnd}
    >
      <SortableContext items={panels.map((p) => p.id)} strategy={rectSortingStrategy}>
        <div className="grid grid-cols-2 gap-2 p-3 overflow-y-auto h-full content-start">
          {panels.map((panel, index) => (
            <SortableCard
              key={panel.id}
              panel={panel}
              index={index}
              isSelected={selectedPanelId === panel.id}
              onSelect={onSelectPanel}
            />
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}
