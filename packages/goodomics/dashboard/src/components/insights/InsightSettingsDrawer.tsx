/**
 * InsightSettingsDrawer component for configuring insight visualization and result settings.
 */

import { Plus, Settings2, Trash2, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import type {
  AnalysisValue,
  InsightDraft,
  InsightView,
} from "../../lib/insightSchemas";
import { titleCase } from "../../lib/insightBuilder";
import { valueReference } from "../../lib/fieldReferences";
import {
  hasAxes,
  hasRecordColors,
  hasTooltips,
} from "../../lib/insightViewCapabilities";
import { insightViewLabel } from "../../lib/insightViewCatalog";
import { numberValue, recordValue } from "../../lib/valueUtils";
import {
  Button,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui";

export function InsightSettingsButton({
  draft,
  result,
  onChange,
}: {
  draft: InsightDraft;
  result?: Record<string, unknown> | null;
  onChange: (draft: InsightDraft) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button variant="ghost" onClick={() => setOpen(true)}>
        <Settings2 className="h-4 w-4" /> Settings
      </Button>
      {open ? (
        <InsightSettingsDrawer
          draft={draft}
          result={result}
          onChange={onChange}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}

function InsightSettingsDrawer({
  draft,
  result,
  onChange,
  onClose,
}: {
  draft: InsightDraft;
  result?: Record<string, unknown> | null;
  onChange: (draft: InsightDraft) => void;
  onClose: () => void;
}) {
  const diagnostics = recordValue(result?.diagnostics);

  return (
    <div
      className="fixed inset-0 z-[70] flex justify-end bg-black/20"
      onClick={onClose}
    >
      <aside
        aria-label="Visualization settings"
        className="h-full w-[min(440px,94vw)] overflow-y-auto border-l border-[#d6dee8] bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#dce3eb] bg-white px-4 py-3">
          <div>
            <div className="text-sm font-semibold text-[#1f2937]">
              {insightViewLabel(draft.view.kind)} settings
            </div>
            <div className="text-xs text-[#657082]">
              Visualization, formatting, and result rows
            </div>
          </div>
          <Button
            aria-label="Close settings"
            size="icon"
            variant="ghost"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="space-y-6 p-4">
          <ViewSettings draft={draft} onChange={onChange} />
          <ResultRowSettings draft={draft} onChange={onChange} />
          <DrawerSection title="Coverage diagnostics">
            <div className="grid grid-cols-2 gap-2">
              <Diagnostic
                label="Matched"
                value={numberValue(diagnostics?.matched_count)}
              />
              <Diagnostic
                label="Unmatched"
                value={numberValue(diagnostics?.unmatched_count)}
              />
              <Diagnostic
                label="Conflicts"
                value={numberValue(diagnostics?.duplicate_conflict_count)}
              />
              <Diagnostic
                label="Excluded"
                value={numberValue(diagnostics?.rows_excluded)}
              />
            </div>
          </DrawerSection>
        </div>
      </aside>
    </div>
  );
}

function ViewSettings({
  draft,
  onChange,
}: {
  draft: InsightDraft;
  onChange: (draft: InsightDraft) => void;
}) {
  const view = draft.view;
  return (
    <>
      {view.kind === "table" ? (
        <TableSettings draft={draft} onChange={onChange} />
      ) : null}
      {view.kind === "histogram" ? (
        <DrawerSection title="Histogram">
          <Field label="Bins">
            <Input
              min={1}
              max={500}
              type="number"
              value={view.bins}
              onChange={(event) =>
                onChange({
                  ...draft,
                  view: { ...view, bins: clamp(event.target.value, 1, 500) },
                })
              }
            />
          </Field>
        </DrawerSection>
      ) : null}
      {view.kind === "metric" ? (
        <MetricSettings draft={draft} onChange={onChange} />
      ) : null}
      {hasAxes(view) ? (
        <AxisSettings draft={draft} onChange={onChange} />
      ) : null}
      {hasRecordColors(view) ? (
        <ColorSettings draft={draft} onChange={onChange} />
      ) : null}
      {hasTooltips(view) ? (
        <TooltipSettings draft={draft} onChange={onChange} />
      ) : null}
    </>
  );
}

function TableSettings({
  draft,
  onChange,
}: {
  draft: InsightDraft;
  onChange: (draft: InsightDraft) => void;
}) {
  if (draft.view.kind !== "table") return null;
  const view = draft.view;
  const columns = [
    `${draft.analysis.grain}_id`,
    ...draft.analysis.values.map(valueReference),
  ];
  const sorting = view.sorting[0];
  return (
    <>
      <DrawerSection title="Table display">
        <Field label="Missing values">
          <Input
            value={view.null_format}
            onChange={(event) =>
              onChange({
                ...draft,
                view: { ...view, null_format: event.target.value },
              })
            }
          />
        </Field>
        <div className="grid grid-cols-[minmax(0,1fr)_120px] gap-2">
          <Field label="Sort by">
            <Select
              value={sorting?.by ?? "__none__"}
              onValueChange={(by) =>
                onChange({
                  ...draft,
                  view: {
                    ...view,
                    sorting:
                      by === "__none__"
                        ? []
                        : [{ by, direction: sorting?.direction ?? "asc" }],
                  },
                })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">No sorting</SelectItem>
                {columns.map((column) => (
                  <SelectItem key={column} value={column}>
                    {valueLabel(column, draft.analysis.values)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Direction">
            <Select
              disabled={!sorting}
              value={sorting?.direction ?? "asc"}
              onValueChange={(direction: "asc" | "desc") =>
                sorting &&
                onChange({
                  ...draft,
                  view: { ...view, sorting: [{ ...sorting, direction }] },
                })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="asc">Ascending</SelectItem>
                <SelectItem value="desc">Descending</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </div>
      </DrawerSection>
      <DrawerSection title="Number formatting">
        <div className="space-y-2">
          {draft.analysis.values.map((value) => {
            const reference = valueReference(value);
            const format = view.numeric_format[reference];
            return (
              <div
                className="grid grid-cols-[minmax(0,1fr)_120px_78px] items-end gap-2"
                key={reference}
              >
                <div className="truncate pb-2 text-sm font-medium text-[#526071]">
                  {value.label || titleCase(value.field)}
                </div>
                <Select
                  value={format?.style ?? "number"}
                  onValueChange={(
                    style: "number" | "percent" | "scientific" | "compact",
                  ) =>
                    onChange({
                      ...draft,
                      view: {
                        ...view,
                        numeric_format: {
                          ...view.numeric_format,
                          [reference]: { ...format, style },
                        },
                      },
                    })
                  }
                >
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["number", "percent", "scientific", "compact"].map(
                      (style) => (
                        <SelectItem key={style} value={style}>
                          {titleCase(style)}
                        </SelectItem>
                      ),
                    )}
                  </SelectContent>
                </Select>
                <Input
                  aria-label={`${valueLabel(reference, draft.analysis.values)} decimal places`}
                  className="h-9"
                  min={0}
                  max={12}
                  placeholder="Auto"
                  type="number"
                  value={format?.decimals ?? ""}
                  onChange={(event) =>
                    onChange({
                      ...draft,
                      view: {
                        ...view,
                        numeric_format: {
                          ...view.numeric_format,
                          [reference]: {
                            ...format,
                            style: format?.style ?? "number",
                            decimals: event.target.value
                              ? clamp(event.target.value, 0, 12)
                              : undefined,
                          },
                        },
                      },
                    })
                  }
                />
              </div>
            );
          })}
        </div>
      </DrawerSection>
    </>
  );
}

function AxisSettings({
  draft,
  onChange,
}: {
  draft: InsightDraft;
  onChange: (draft: InsightDraft) => void;
}) {
  return (
    <DrawerSection title="Axes">
      <AxisEditor
        axis="x_axis"
        draft={draft}
        label="X axis"
        onChange={onChange}
      />
      <AxisEditor
        axis="y_axis"
        draft={draft}
        label="Y axis"
        onChange={onChange}
      />
    </DrawerSection>
  );
}

function AxisEditor({
  axis,
  draft,
  label,
  onChange,
}: {
  axis: "x_axis" | "y_axis";
  draft: InsightDraft;
  label: string;
  onChange: (draft: InsightDraft) => void;
}) {
  const view = draft.view;
  if (!hasAxes(view)) return null;
  const current = view[axis];
  const update = (patch: Record<string, unknown>) =>
    onChange({
      ...draft,
      view: {
        ...view,
        [axis]: { ...(current ?? {}), ...patch },
      } as InsightView,
    });
  return (
    <div className="space-y-2 rounded-md border border-[#dce3eb] p-3">
      <div className="text-xs font-semibold text-[#526071]">{label}</div>
      <Input
        placeholder="Axis label"
        value={current?.label ?? ""}
        onChange={(event) => update({ label: event.target.value || undefined })}
      />
      <div className="grid grid-cols-3 gap-2">
        <Select
          value={current?.scale ?? "linear"}
          onValueChange={(scale) => update({ scale })}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {["linear", "log", "category", "time"].map((scale) => (
              <SelectItem key={scale} value={scale}>
                {titleCase(scale)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          placeholder="Min"
          type="number"
          value={current?.minimum ?? ""}
          onChange={(event) =>
            update({ minimum: optionalNumber(event.target.value) })
          }
        />
        <Input
          placeholder="Max"
          type="number"
          value={current?.maximum ?? ""}
          onChange={(event) =>
            update({ maximum: optionalNumber(event.target.value) })
          }
        />
      </div>
    </div>
  );
}

function MetricSettings({
  draft,
  onChange,
}: {
  draft: InsightDraft;
  onChange: (draft: InsightDraft) => void;
}) {
  if (draft.view.kind !== "metric") return null;
  const view = draft.view;
  const format = view.number_format;
  return (
    <>
      <DrawerSection title="Number format">
        <div className="grid grid-cols-2 gap-2">
          <Select
            value={format?.style ?? "number"}
            onValueChange={(
              style: "number" | "percent" | "scientific" | "compact",
            ) =>
              onChange({
                ...draft,
                view: { ...view, number_format: { ...format, style } },
              })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {["number", "percent", "scientific", "compact"].map((style) => (
                <SelectItem key={style} value={style}>
                  {titleCase(style)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            min={0}
            max={12}
            placeholder="Auto decimals"
            type="number"
            value={format?.decimals ?? ""}
            onChange={(event) =>
              onChange({
                ...draft,
                view: {
                  ...view,
                  number_format: {
                    style: format?.style ?? "number",
                    ...format,
                    decimals: event.target.value
                      ? clamp(event.target.value, 0, 12)
                      : undefined,
                  },
                },
              })
            }
          />
        </div>
      </DrawerSection>
      <DrawerSection title="Thresholds">
        <div className="space-y-2">
          {view.thresholds.map((threshold, index) => (
            <div
              className="grid grid-cols-[90px_minmax(0,1fr)_42px_32px] gap-1.5"
              key={index}
            >
              <Input
                aria-label="Threshold value"
                type="number"
                value={threshold.value}
                onChange={(event) => {
                  const thresholds = view.thresholds.map((item, itemIndex) =>
                    itemIndex === index
                      ? { ...item, value: Number(event.target.value) }
                      : item,
                  );
                  onChange({ ...draft, view: { ...view, thresholds } });
                }}
              />
              <Input
                placeholder="Label"
                value={threshold.label ?? ""}
                onChange={(event) => {
                  const thresholds = view.thresholds.map((item, itemIndex) =>
                    itemIndex === index
                      ? { ...item, label: event.target.value || undefined }
                      : item,
                  );
                  onChange({ ...draft, view: { ...view, thresholds } });
                }}
              />
              <input
                aria-label="Threshold color"
                className="h-9 w-10"
                type="color"
                value={threshold.color ?? "#16784a"}
                onChange={(event) => {
                  const thresholds = view.thresholds.map((item, itemIndex) =>
                    itemIndex === index
                      ? { ...item, color: event.target.value }
                      : item,
                  );
                  onChange({ ...draft, view: { ...view, thresholds } });
                }}
              />
              <Button
                aria-label="Remove threshold"
                className="h-9 w-8"
                size="icon"
                variant="ghost"
                onClick={() =>
                  onChange({
                    ...draft,
                    view: {
                      ...view,
                      thresholds: view.thresholds.filter(
                        (_, itemIndex) => itemIndex !== index,
                      ),
                    },
                  })
                }
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              onChange({
                ...draft,
                view: {
                  ...view,
                  thresholds: [...view.thresholds, { value: 0 }],
                },
              })
            }
          >
            <Plus className="h-4 w-4" /> Add threshold
          </Button>
        </div>
      </DrawerSection>
    </>
  );
}

function ColorSettings({
  draft,
  onChange,
}: {
  draft: InsightDraft;
  onChange: (draft: InsightDraft) => void;
}) {
  if (!hasRecordColors(draft.view)) return null;
  const view = draft.view;
  return (
    <DrawerSection title="Series colors">
      <div className="space-y-1.5">
        {draft.analysis.values.map((value, index) => {
          const reference = valueReference(value);
          return (
            <label
              className="flex items-center justify-between rounded-md border border-[#dce3eb] px-3 py-2"
              key={reference}
            >
              <span className="truncate text-sm text-[#526071]">
                {value.label || titleCase(value.field)}
              </span>
              <input
                className="h-7 w-10 cursor-pointer"
                type="color"
                value={view.colors[reference] ?? fallbackColor(index)}
                onChange={(event) =>
                  onChange({
                    ...draft,
                    view: {
                      ...view,
                      colors: {
                        ...view.colors,
                        [reference]: event.target.value,
                      },
                    },
                  })
                }
              />
            </label>
          );
        })}
      </div>
    </DrawerSection>
  );
}

function TooltipSettings({
  draft,
  onChange,
}: {
  draft: InsightDraft;
  onChange: (draft: InsightDraft) => void;
}) {
  if (!hasTooltips(draft.view)) return null;
  const view = draft.view;
  return (
    <DrawerSection title="Tooltips">
      <div className="space-y-1.5">
        {draft.analysis.values.map((value) => {
          const reference = valueReference(value);
          return (
            <label
              className="flex items-center gap-2 rounded-md border border-[#dce3eb] px-3 py-2 text-sm"
              key={reference}
            >
              <input
                checked={view.tooltips.includes(reference)}
                type="checkbox"
                onChange={() =>
                  onChange({
                    ...draft,
                    view: {
                      ...view,
                      tooltips: view.tooltips.includes(reference)
                        ? view.tooltips.filter((id) => id !== reference)
                        : [...view.tooltips, reference],
                    },
                  })
                }
              />
              {value.label || titleCase(value.field)}
            </label>
          );
        })}
      </div>
    </DrawerSection>
  );
}

function ResultRowSettings({
  draft,
  onChange,
}: {
  draft: InsightDraft;
  onChange: (draft: InsightDraft) => void;
}) {
  return (
    <DrawerSection title="Result rows">
      <Field label="Row limit">
        <Input
          min={1}
          max={10_000}
          type="number"
          value={draft.analysis.limit}
          onChange={(event) =>
            onChange({
              ...draft,
              analysis: {
                ...draft.analysis,
                limit: clamp(event.target.value, 1, 10_000),
              },
            })
          }
        />
      </Field>
      <label className="flex items-center gap-2 text-sm text-[#374151]">
        <input
          checked={draft.analysis.random}
          type="checkbox"
          onChange={(event) =>
            onChange({
              ...draft,
              analysis: { ...draft.analysis, random: event.target.checked },
            })
          }
        />
        Select result rows randomly
      </label>
    </DrawerSection>
  );
}

function DrawerSection({
  children,
  title,
}: {
  children: ReactNode;
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

function Field({ children, label }: { children: ReactNode; label: string }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-semibold text-[#657082]">{label}</span>
      {children}
    </label>
  );
}

function Diagnostic({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded-md border border-[#dce3eb] bg-[#f8fafc] p-2">
      <div className="text-xs text-[#657082]">{label}</div>
      <div className="font-semibold text-[#1f2937]">{value ?? "n/a"}</div>
    </div>
  );
}

function valueLabel(id: string, values: AnalysisValue[]) {
  const value = values.find((item) => valueReference(item) === id);
  return value?.label || (value ? titleCase(value.field) : titleCase(id));
}

function optionalNumber(value: string) {
  return value.trim() && Number.isFinite(Number(value))
    ? Number(value)
    : undefined;
}

function clamp(value: string, minimum: number, maximum: number) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return minimum;
  return Math.min(Math.max(parsed, minimum), maximum);
}

function fallbackColor(index: number) {
  return ["#38BDF8", "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A"][
    index % 6
  ];
}
