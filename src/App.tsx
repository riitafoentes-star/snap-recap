import React from "react";
import { NavigationSidebar } from "./components/NavigationSidebar";
import { usePipelineStore } from "./store/pipelineStore";
import { IngestionScreen } from "./screens/IngestionScreen";
import { IntelligenceScreen } from "./screens/IntelligenceScreen";
import { ProductionScreen } from "./screens/ProductionScreen";

function App(): React.ReactElement {
  const currentPhase = usePipelineStore((s) => s.currentPhase);

  return (
    <div className="flex h-screen w-screen bg-bg-base text-text-primary overflow-hidden">
      <NavigationSidebar />
      <main className="flex flex-1 overflow-hidden">
        {currentPhase === "ingestion" && <IngestionScreen />}
        {currentPhase === "intelligence" && <IntelligenceScreen />}
        {currentPhase === "production" && <ProductionScreen />}
      </main>
    </div>
  );
}

export default App;
