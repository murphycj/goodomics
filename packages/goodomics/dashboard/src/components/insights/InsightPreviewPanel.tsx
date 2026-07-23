import { Card, CardContent } from "../ui";
import { InsightPreview } from "../reports/InsightPreview";
import {
  numberValue,
  recordValue,
  stringValue,
} from "../../lib/valueUtils";

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
  const linker = recordValue(result?.linker) ?? recordValue(config.linker);
  const diagnostics = recordValue(result?.linker_diagnostics);
  const resultDiagnostics = Array.isArray(result?.result_selection_diagnostics)
    ? result.result_selection_diagnostics.map(recordValue).filter(Boolean)
    : [];
  const policy =
    recordValue(result?.result_policy) ?? recordValue(config.result_policy);
  const filters = Array.isArray(result?.filters)
    ? result.filters
    : Array.isArray(config.filters)
      ? config.filters
      : [];
  const chips = [
    sampleSelectionLabel(filters),
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

// reads the filters and returns a label describing the sample selection
function sampleSelectionLabel(filters: unknown[]) {
  // read the filters and extract the sample references
  const references = filters
    .map(recordValue)
    .filter((filter) => filter?.field === "sample")
    .flatMap((filter) =>
      Array.isArray(filter?.value)
        ? filter.value.map(recordValue).filter(Boolean)
        : [],
    );

  const samples = references.filter(
    (reference) => reference?.kind === "sample",
  );
  const groups = references.filter(
    (reference) => reference?.kind === "sample_group",
  );

  if (!samples.length && !groups.length) return "All samples";

  const labels = [];
  if (samples.length)
    labels.push(`${samples.length} sample${samples.length === 1 ? "" : "s"}`);
  if (groups.length)
    labels.push(
      `${groups.length} sample group${groups.length === 1 ? "" : "s"}`,
    );
  return labels.join(" + ");
}

function resultDiagnosticLabels(diagnostics: Record<string, unknown> | null) {
  if (!diagnostics) return [];
  const labels: string[] = [];
  const selection = stringValue(diagnostics.selection);
  const missing = stringArrayValue(diagnostics.missing_samples);
  const warnings = stringArrayValue(diagnostics.warnings);
  const versions = recordValue(diagnostics.versions);
  if (selection) labels.push(`Results ${selection.replaceAll("_", " ")}`);
  if (versions) labels.push(`${Object.keys(versions).length} method versions`);
  if (missing.length) labels.push(`${missing.length} samples missing`);
  labels.push(...warnings);
  return labels;
}

function stringArrayValue(value: unknown) {
  return Array.isArray(value)
    ? value.filter(
        (item): item is string => typeof item === "string" && Boolean(item),
      )
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
  return count === null
    ? `Data size ${mode}`
    : `Data size ${mode}: ${count} rows`;
}

function diagnosticsLabel(diagnostics: Record<string, unknown> | null) {
  const matched = numberValue(diagnostics?.matched_count);
  if (matched === null) return null;
  const unmatched = numberValue(diagnostics?.unmatched_count) ?? 0;
  const conflicts = numberValue(diagnostics?.duplicate_conflict_count) ?? 0;
  return `Matched ${matched}; unmatched ${unmatched}; conflicts ${conflicts}`;
}
