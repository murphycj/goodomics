import { Settings2, X } from "lucide-react";
import { useState } from "react";
import type { DisplayOptions } from "../../lib/insightDisplayOptions";
import { DISPLAY_OPTION_ITEMS } from "../../lib/insightDisplayOptions";
import { numberValue, recordValue } from "../../lib/valueUtils";
import {
  Button,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui";

type ResultPolicyMode =
  | "preview"
  | "more_rows"
  | "random_sample"
  | "all_rows"
  | "export_full_data";

export function InsightChartControls({
  config,
  displayOptions,
  randomSeed,
  result,
  resultPolicyMode,
  rowLimit,
  onRandomSeedChange,
  onDisplayOptionsChange,
  onResultPolicyModeChange,
  onRowLimitChange,
}: {
  config?: Record<string, unknown>;
  displayOptions: DisplayOptions;
  randomSeed: string;
  result?: Record<string, unknown> | null;
  resultPolicyMode: ResultPolicyMode;
  rowLimit: number;
  onRandomSeedChange: (value: string) => void;
  onDisplayOptionsChange: React.Dispatch<React.SetStateAction<DisplayOptions>>;
  onResultPolicyModeChange: (value: ResultPolicyMode) => void;
  onRowLimitChange: (value: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <SettingsDrawerButton
        config={config}
        options={displayOptions}
        randomSeed={randomSeed}
        result={result}
        resultPolicyMode={resultPolicyMode}
        rowLimit={rowLimit}
        onChange={onDisplayOptionsChange}
        onRandomSeedChange={onRandomSeedChange}
        onResultPolicyModeChange={onResultPolicyModeChange}
        onRowLimitChange={onRowLimitChange}
      />
    </div>
  );
}

function SettingsDrawerButton({
  config,
  options,
  randomSeed,
  result,
  resultPolicyMode,
  rowLimit,
  onChange,
  onRandomSeedChange,
  onResultPolicyModeChange,
  onRowLimitChange,
}: {
  config?: Record<string, unknown>;
  options: DisplayOptions;
  randomSeed: string;
  result?: Record<string, unknown> | null;
  resultPolicyMode: ResultPolicyMode;
  rowLimit: number;
  onChange: React.Dispatch<React.SetStateAction<DisplayOptions>>;
  onRandomSeedChange: (value: string) => void;
  onResultPolicyModeChange: (value: ResultPolicyMode) => void;
  onRowLimitChange: (value: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const diagnostics = recordValue(result?.linker_diagnostics);
  const policy =
    recordValue(result?.result_policy) ?? recordValue(config?.result_policy);
  return (
    <>
      <Button
        aria-label="Chart settings"
        variant="ghost"
        onClick={() => setOpen((current) => !current)}
      >
        <Settings2 className="h-4 w-4" /> Settings
      </Button>
      <div
        aria-hidden={!open}
        className={[
          "fixed inset-0 z-50 flex justify-end bg-black/20 transition-opacity duration-150 ease-out",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        ].join(" ")}
        onClick={() => setOpen(false)}
      >
        <aside
          className={[
            "h-full w-[min(420px,92vw)] overflow-y-auto border-l border-[#d6dee8] bg-white shadow-xl transition-transform duration-150 ease-out",
            open ? "translate-x-0" : "translate-x-full",
          ].join(" ")}
          onClick={(event) => event.stopPropagation()}
        >
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#dce3eb] bg-white px-4 py-3">
              <div>
                <div className="text-sm font-semibold text-[#1f2937]">
                  Chart settings
                </div>
                <div className="text-xs text-[#657082]">
                  Display, axes, data size, and linker diagnostics
                </div>
              </div>
              <Button
                aria-label="Close settings"
                size="icon"
                variant="ghost"
                onClick={() => setOpen(false)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="space-y-5 p-4">
              <DrawerSection title="Chart display">
                <div className="grid gap-2">
                  {DISPLAY_OPTION_ITEMS.map((item) => (
                    <label
                      className="flex items-center justify-between gap-3 rounded-md border border-[#dce3eb] px-3 py-2 text-sm"
                      key={item.key}
                    >
                      <span>{item.label}</span>
                      <input
                        checked={Boolean(options[item.key])}
                        type="checkbox"
                        onChange={() =>
                          onChange((current) => {
                            const currentValue = current[item.key];
                            if (typeof currentValue !== "boolean") return current;
                            return {
                              ...current,
                              [item.key]: !currentValue,
                            };
                          })
                        }
                      />
                    </label>
                  ))}
                </div>
              </DrawerSection>
              <DrawerSection title="Axes">
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <div className="text-xs font-semibold uppercase tracking-wide text-[#657082]">
                      X-axis label
                    </div>
                    <Input
                      className="h-9"
                      placeholder="X-axis label"
                      value={options.xAxisLabel}
                      onChange={(event) =>
                        onChange((current) => ({
                          ...current,
                          xAxisLabel: event.target.value,
                        }))
                      }
                      onKeyDown={(event) => event.stopPropagation()}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <div className="text-xs font-semibold uppercase tracking-wide text-[#657082]">
                      Y-axis label
                    </div>
                    <Input
                      className="h-9"
                      placeholder="Y-axis label"
                      value={options.yAxisLabel}
                      onChange={(event) =>
                        onChange((current) => ({
                          ...current,
                          yAxisLabel: event.target.value,
                        }))
                      }
                      onKeyDown={(event) => event.stopPropagation()}
                    />
                  </div>
                </div>
              </DrawerSection>
              <DrawerSection title="Scale">
                <div className="grid grid-cols-2 gap-1">
                  {(["linear", "log"] as const).map((scale) => (
                    <button
                      className={[
                        "h-9 rounded-md border px-3 text-sm font-semibold transition-colors",
                        options.yAxisScale === scale
                          ? "border-[#16784a] bg-[#e8f5ee] text-[#16784a]"
                          : "border-[#d6dee8] bg-white text-[#526071] hover:bg-[#f8fafc]",
                      ].join(" ")}
                      key={scale}
                      type="button"
                      onClick={() =>
                        onChange((current) => ({
                          ...current,
                          yAxisScale: scale,
                        }))
                      }
                    >
                      {scale === "linear" ? "Linear" : "Logarithmic"}
                    </button>
                  ))}
                </div>
              </DrawerSection>
              <DrawerSection title="Data size">
                <div className="space-y-3">
                  <Select
                    value={resultPolicyMode}
                    onValueChange={(value) =>
                      onResultPolicyModeChange(value as ResultPolicyMode)
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="preview">Preview default</SelectItem>
                      <SelectItem value="more_rows">More rows</SelectItem>
                      <SelectItem value="random_sample">Random sample</SelectItem>
                      <SelectItem value="all_rows">All rows</SelectItem>
                      <SelectItem value="export_full_data">Export full data</SelectItem>
                    </SelectContent>
                  </Select>
                  {resultPolicyMode === "more_rows" ||
                  resultPolicyMode === "random_sample" ? (
                    <Input
                      inputMode="numeric"
                      min={1}
                      max={10000}
                      type="number"
                      value={rowLimit}
                      onChange={(event) =>
                        onRowLimitChange(
                          clampNumber(event.target.value, 1, 10000),
                        )
                      }
                    />
                  ) : null}
                  {resultPolicyMode === "random_sample" ? (
                    <Input
                      value={randomSeed}
                      onChange={(event) =>
                        onRandomSeedChange(event.target.value)
                      }
                    />
                  ) : null}
                  {policy ? (
                    <p className="m-0 text-xs text-[#657082]">
                      Embedded {numberValue(policy.embedded_row_count) ?? 0} of{" "}
                      {numberValue(policy.source_row_count) ?? 0} rows.
                    </p>
                  ) : null}
                </div>
              </DrawerSection>
              <DrawerSection title="Linker diagnostics">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <DiagnosticChip
                    label="Matched"
                    value={numberValue(diagnostics?.matched_count)}
                  />
                  <DiagnosticChip
                    label="Unmatched"
                    value={numberValue(diagnostics?.unmatched_count)}
                  />
                  <DiagnosticChip
                    label="Conflicts"
                    value={numberValue(diagnostics?.duplicate_conflict_count)}
                  />
                  <DiagnosticChip
                    label="Excluded"
                    value={numberValue(diagnostics?.rows_excluded)}
                  />
                </div>
              </DrawerSection>
            </div>
        </aside>
      </div>
    </>
  );
}

function DrawerSection({
  children,
  title,
}: {
  children: React.ReactNode;
  title: string;
}) {
  return (
    <section className="space-y-2">
      <h3 className="m-0 text-xs font-bold uppercase tracking-wide text-[#657082]">
        {title}
      </h3>
      {children}
    </section>
  );
}

function DiagnosticChip({
  label,
  value,
}: {
  label: string;
  value: number | null;
}) {
  return (
    <div className="rounded-md border border-[#dce3eb] bg-[#f8fafc] p-2">
      <div className="text-xs text-[#657082]">{label}</div>
      <div className="font-semibold text-[#1f2937]">{value ?? "n/a"}</div>
    </div>
  );
}

function clampNumber(value: string, min: number, max: number) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return min;
  return Math.min(Math.max(parsed, min), max);
}
