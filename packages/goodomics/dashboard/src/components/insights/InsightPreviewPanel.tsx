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
  const resultDiagnostics = Array.isArray(result?.result_selection_diagnostics)
    ? result.result_selection_diagnostics.map(readRecord).filter(Boolean)
    : [];
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
    ...resultDiagnostics.flatMap((item) => resultDiagnosticLabels(item)),
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
  const kind = stringValue(context?.kind) || "sample_group";
  const sampleGroup = stringValue(context?.sample_group_id);
  const sample = stringValue(context?.sample_id);
  const sampleGroups = stringArrayValue(context?.sample_group_ids);
  const samples = stringArrayValue(context?.sample_ids);
  if (samples.length > 1) return `${samples.length} samples`;
  if (sampleGroups.length > 1) return `${sampleGroups.length} sample groups`;
  if (sample) return `Sample ${sample}`;
  if (sampleGroup) return `Sample group ${sampleGroup}`;
  return kind === "sample" ? "Sample context" : "All samples";
}

function resultDiagnosticLabels(diagnostics: Record<string, unknown> | null) {
  if (!diagnostics) return [];
  const labels: string[] = [];
  const selection = stringValue(diagnostics.selection);
  const missing = stringArrayValue(diagnostics.missing_samples);
  const warnings = stringArrayValue(diagnostics.warnings);
  const versions = readRecord(diagnostics.versions);
  if (selection) labels.push(`Results ${selection.replaceAll("_", " ")}`);
  if (versions) labels.push(`${Object.keys(versions).length} method versions`);
  if (missing.length) labels.push(`${missing.length} samples missing`);
  labels.push(...warnings);
  return labels;
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
