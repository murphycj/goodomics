import type { DisplayOptions } from "../../lib/insightDisplayOptions";
import { Card, CardContent } from "../ui";
import { InsightPreview } from "../reports/InsightPreview";
import { InsightChartControls } from "./InsightChartControls";

export function InsightPreviewPanel({
  title,
  isCached,
  error,
  config,
  result,
  setupWarning,
  displayOptions,
  onDisplayOptionsChange,
  visualization,
  onVisualizationChange,
}: {
  title: string;
  isCached: boolean;
  error: Error | null;
  config: Record<string, unknown>;
  result: Record<string, unknown> | null | undefined;
  setupWarning: string | null;
  displayOptions: DisplayOptions;
  onDisplayOptionsChange: React.Dispatch<React.SetStateAction<DisplayOptions>>;
  visualization: string;
  onVisualizationChange: (value: string) => void;
}) {
  return (
    <Card className="mt-0 min-h-0 overflow-hidden p-0">
      <CardContent className="flex h-full min-h-0 flex-col">
        <div className="flex items-center justify-between border-b border-[#dce3eb] px-4 py-3">
          <div>
            <h2 className="m-0 text-base font-semibold">{title}</h2>
            <p className="m-0 text-xs text-[#657082]">
              {isCached ? "Using cached result" : "Preview result"}
            </p>
          </div>
          <InsightChartControls
            displayOptions={displayOptions}
            onDisplayOptionsChange={onDisplayOptionsChange}
            visualization={visualization}
            onVisualizationChange={onVisualizationChange}
          />
        </div>
        <div className="min-h-0 flex-1 p-4">
          {error ? (
            <div className="rounded-md border border-[#fecaca] bg-[#fff1f2] p-3 text-sm text-[#b42318]">
              {error.message}
            </div>
          ) : (
            <InsightPreview
              config={config}
              result={result}
              setupWarning={setupWarning}
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
