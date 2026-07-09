import { Card, CardContent } from "../ui";
import { InsightPreview } from "../reports/InsightPreview";

export function InsightPreviewPanel({
  error,
  config,
  result,
  setupWarning,
  tableActions,
}: {
  error: Error | null;
  config: Record<string, unknown>;
  result: Record<string, unknown> | null | undefined;
  setupWarning: string | null;
  tableActions?: {
    addLabel: string;
    emptyLabel?: string;
    onAddColumn: () => void;
  };
}) {
  return (
    <Card className="mt-0 h-full min-h-0 overflow-hidden p-0">
      <CardContent className="flex h-full min-h-0 flex-col">
        <div className="min-h-0 flex-1 overflow-hidden p-1.5">
          {error ? (
            <div className="rounded-md border border-[#fecaca] bg-[#fff1f2] p-3 text-sm text-[#b42318]">
              {error.message}
            </div>
          ) : (
            <InsightPreview
              config={config}
              result={result}
              setupWarning={setupWarning}
              tableActions={tableActions}
            />
          )}
        </div>
        <PreviewAuditBar config={config} result={result} />
      </CardContent>
    </Card>
  );
}

function PreviewAuditBar({
  config,
  result,
}: {
  config: Record<string, unknown>;
  result: Record<string, unknown> | null | undefined;
}) {
  const context = readRecord(result?.context) ?? readRecord(config.context);
  const linker = readRecord(result?.linker) ?? readRecord(config.linker);
  const diagnostics = readRecord(result?.linker_diagnostics);
  const policy = readRecord(result?.result_policy) ?? readRecord(config.result_policy);
  const filters = Array.isArray(result?.filters)
    ? result.filters
    : Array.isArray(config.filters)
      ? config.filters
      : [];
  const chips = [
    contextLabel(context),
    linkerLabel(linker),
    filters.length ? `${filters.length} filters` : "No filters",
    policyLabel(policy),
    diagnosticsLabel(diagnostics),
  ].filter(Boolean);
  if (chips.length === 0) return null;
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-1.5 border-t border-[#dce3eb] bg-[#f8fafc] px-2 py-1.5">
      {chips.map((chip) => (
        <span
          className="rounded-md border border-[#d6dee8] bg-white px-2 py-1 text-xs text-[#4f5b6b]"
          key={chip}
        >
          {chip}
        </span>
      ))}
    </div>
  );
}

function contextLabel(context: Record<string, unknown> | null) {
  const kind = stringValue(context?.kind) || "cohort";
  const sampleSet = stringValue(context?.sample_set_id);
  const sample = stringValue(context?.sample_id);
  const runSample = stringValue(context?.run_sample_id);
  const sampleSets = stringArrayValue(context?.sample_set_ids);
  const samples = stringArrayValue(context?.sample_ids);
  const runSamples = stringArrayValue(context?.run_sample_ids);
  if (samples.length > 1) return `${samples.length} samples`;
  if (runSamples.length > 1) return `${runSamples.length} run samples`;
  if (sampleSets.length > 1) return `${sampleSets.length} sample groups`;
  if (sample) return `Sample ${sample}`;
  if (runSample) return `Run sample ${runSample}`;
  if (sampleSet) return `Sample group ${sampleSet}`;
  return kind === "sample" ? "Sample context" : "All samples";
}

function stringArrayValue(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && Boolean(item))
    : [];
}

function linkerLabel(linker: Record<string, unknown> | null) {
  const kind = stringValue(linker?.kind);
  if (!kind || kind === "none") return null;
  return `Matched by ${kind.replace("_", " ")}`;
}

function policyLabel(policy: Record<string, unknown> | null) {
  const mode = stringValue(policy?.mode);
  const count = numberValue(policy?.embedded_row_count);
  if (!mode) return null;
  return count === null ? `Data size ${mode}` : `Data size ${mode}: ${count} rows`;
}

function diagnosticsLabel(diagnostics: Record<string, unknown> | null) {
  const matched = numberValue(diagnostics?.matched_count);
  if (matched === null) return null;
  const unmatched = numberValue(diagnostics?.unmatched_count) ?? 0;
  const conflicts = numberValue(diagnostics?.duplicate_conflict_count) ?? 0;
  return `Matched ${matched}; unmatched ${unmatched}; conflicts ${conflicts}`;
}

function readRecord(value: unknown) {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
