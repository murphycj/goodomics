/**
 * InsightValueEditor component for editing insight values.
 */

import {
  ChevronDown,
  ChevronUp,
  Copy,
  Eye,
  EyeOff,
  GripVertical,
  MoreHorizontal,
  Plus,
  Settings2,
  Trash2,
  X,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import {
  requiredViewBindingIds,
  type AnalysisValue,
  type InsightDraft,
  type InsightView,
} from "../../lib/insightSchemas";
import {
  appendValueToView,
  reconcileView,
  replaceViewReference,
  safeValueAlias,
  titleCase,
} from "../../lib/insightBuilder";
import { CHART_COLORS } from "../../lib/chartColors";
import { parseFieldReference, valueReference } from "../../lib/fieldReferences";
import {
  hasCategoryBinding,
  hasRecordColors,
  type CategoryBindingView,
} from "../../lib/insightViewCapabilities";
import { getInsightViewDefinition } from "../../lib/insightViewCatalog";
import {
  Badge,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui";
import {
  InsightValuePicker,
  isInsightPickerOptionCompatible,
  type InsightPickerOption,
} from "./InsightValuePicker";

export function InsightValueEditor({
  draft,
  options,
  pickerStatus,
  onChange,
  onEditScope,
}: {
  draft: InsightDraft;
  options: InsightPickerOption[];
  pickerStatus: "loading" | "error" | "ready";
  onChange: (draft: InsightDraft) => void;
  onEditScope: (id: string) => void;
}) {
  const [activeValueId, setActiveValueId] = useState<string | null>(null);
  const [manage, setManage] = useState(false);
  const [managedIds, setManagedIds] = useState<Set<string>>(new Set());
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const optionBySource = useMemo(
    () => new Map(options.map((option) => [sourceKey(option.value), option])),
    [options],
  );
  const isTable = draft.view.kind === "table";
  const viewDefinition = getInsightViewDefinition(draft.view.kind);
  const title = viewDefinition.editor.title;
  const addLabel = viewDefinition.editor.addLabel;

  const addOptions = (selected: InsightPickerOption[]) => {
    let next = draft;
    for (const option of selected) {
      const alias = next.analysis.values.some(
        (value) => valueReference(value) === option.value.field,
      )
        ? safeValueAlias(
            option.fieldId,
            next.analysis.values,
            next.analysis.grain,
          )
        : undefined;
      const value = {
        ...option.value,
        ...(alias ? { as: alias } : {}),
      } as AnalysisValue;
      const reference = valueReference(value);
      const values = [...next.analysis.values, value];
      next = {
        ...next,
        analysis: { ...next.analysis, values },
        view: appendValueToView(
          next.view,
          reference,
          values,
          next.analysis.grain,
        ),
      };
    }
    onChange(next);
  };

  const removeIds = (ids: Set<string>) => {
    const values = draft.analysis.values.filter(
      (value) => !ids.has(valueReference(value)),
    );
    onChange({
      ...draft,
      analysis: { ...draft.analysis, values },
      view: reconcileView(draft.view, values, draft.analysis.grain),
    });
    setManagedIds(new Set());
    if (activeValueId && ids.has(activeValueId)) setActiveValueId(null);
  };

  const updateValue = (id: string, patch: Partial<AnalysisValue>) => {
    onChange({
      ...draft,
      analysis: {
        ...draft.analysis,
        values: draft.analysis.values.map((value) =>
          valueReference(value) === id
            ? ({ ...value, ...patch } as AnalysisValue)
            : value,
        ),
      },
    });
  };

  // Replace an existing value with a new one
  const replaceValue = (id: string, option: InsightPickerOption) => {
    const current = draft.analysis.values.find(
      (value) => valueReference(value) === id,
    );
    if (!current) return;

    const otherReferences = new Set(
      draft.analysis.values
        .filter((value) => value !== current)
        .map(valueReference),
    );

    const alias =
      current.as ??
      (otherReferences.has(option.value.field)
        ? safeValueAlias(
            option.fieldId,
            draft.analysis.values,
            draft.analysis.grain,
          )
        : undefined);

    const replacement = {
      ...option.value,
      ...(alias ? { as: alias } : {}),
      label: current.label,
    } as AnalysisValue;
    const nextReference = valueReference(replacement);
    const values = draft.analysis.values.map((value) =>
      valueReference(value) === id ? replacement : value,
    );

    onChange({
      ...draft,
      analysis: { ...draft.analysis, values },
      view: reconcileView(
        replaceViewReference(draft.view, id, nextReference),
        values,
        draft.analysis.grain,
      ),
    });
  };

  // Duplicate an existing value
  const duplicateValue = (id: string) => {
    const index = draft.analysis.values.findIndex(
      (value) => valueReference(value) === id,
    );
    const source = draft.analysis.values[index];
    if (!source) return;

    const nextId = safeValueAlias(
      sourceFieldId(source),
      draft.analysis.values,
      draft.analysis.grain,
    );

    const duplicate = {
      ...source,
      as: nextId,
      label: `${displayLabel(source, optionBySource)} copy`,
      filters: source.filters.map((filter) => ({ ...filter })),
      scope: source.scope ? { ...source.scope } : undefined,
    } as AnalysisValue;

    const values = [
      ...draft.analysis.values.slice(0, index + 1),
      duplicate,
      ...draft.analysis.values.slice(index + 1),
    ];

    onChange({
      ...draft,
      analysis: { ...draft.analysis, values },
      view: appendValueToView(draft.view, nextId, values, draft.analysis.grain),
    });
  };

  const moveValue = (id: string, offset: number) => {
    const from = draft.analysis.values.findIndex(
      (value) => valueReference(value) === id,
    );
    const to = Math.max(
      0,
      Math.min(draft.analysis.values.length - 1, from + offset),
    );
    if (from < 0 || from === to) return;
    const values = [...draft.analysis.values];
    const [value] = values.splice(from, 1);
    values.splice(to, 0, value);
    onChange({ ...draft, analysis: { ...draft.analysis, values } });
  };

  const toggleVisibility = (id: string) => {
    if (requiredViewBindingIds(draft.view).has(id)) return;
    const hidden = new Set(draft.view.hidden_values);
    if (hidden.has(id)) hidden.delete(id);
    else hidden.add(id);
    const hiddenValues = draft.analysis.values
      .map(valueReference)
      .filter((valueId) => hidden.has(valueId));
    onChange({
      ...draft,
      view: { ...draft.view, hidden_values: hiddenValues },
    });
  };

  const activeValue = draft.analysis.values.find(
    (value) => valueReference(value) === activeValueId,
  );
  const activeOption = activeValue
    ? optionBySource.get(sourceKey(activeValue))
    : undefined;

  return (
    <section className="space-y-3">
      <ViewBindings draft={draft} onChange={onChange} />
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="m-0 text-xs font-bold uppercase tracking-wide text-[#526071]">
            {title}
          </h2>
          {isTable ? (
            <p className="mb-0 mt-0.5 text-xs text-[#758195]">
              Row identity: {titleCase(draft.analysis.grain)}
            </p>
          ) : null}
        </div>
        {draft.analysis.values.length ? (
          <Button
            className="h-7 px-2 text-xs"
            variant="ghost"
            onClick={() => {
              setManage((current) => !current);
              setManagedIds(new Set());
            }}
          >
            {manage ? "Done" : "Manage"}
          </Button>
        ) : null}
      </div>
      <div className="space-y-1.5">
        {draft.analysis.values.map((value, index) => {
          const reference = valueReference(value);
          const option = optionBySource.get(sourceKey(value));
          const color = colorForValue(draft.view, reference, index);
          const visible = !draft.view.hidden_values.includes(reference);
          const required = requiredViewBindingIds(draft.view).has(reference);
          return (
            <div
              className="group flex min-h-11 items-center gap-2 rounded-md border border-[#dce3eb] bg-white px-2 py-1.5 shadow-sm transition-colors hover:border-[#b9c6d5]"
              draggable={!manage}
              key={reference}
              onDragStart={() => setDraggedId(reference)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => {
                if (!draggedId || draggedId === reference) return;
                const from = draft.analysis.values.findIndex(
                  (item) => valueReference(item) === draggedId,
                );
                moveValue(draggedId, index - from);
                setDraggedId(null);
              }}
            >
              {manage ? (
                <input
                  aria-label={`Select ${displayLabel(value, optionBySource)}`}
                  checked={managedIds.has(reference)}
                  type="checkbox"
                  onChange={() =>
                    setManagedIds((current) => {
                      const next = new Set(current);
                      if (next.has(reference)) next.delete(reference);
                      else next.add(reference);
                      return next;
                    })
                  }
                />
              ) : (
                <GripVertical className="h-4 w-4 shrink-0 cursor-grab text-[#a2adba] opacity-0 group-hover:opacity-100" />
              )}
              <button
                aria-label={
                  required
                    ? `${displayLabel(value, optionBySource)} is required by this view`
                    : visible
                      ? `Hide ${isTable ? "column" : "series"}`
                      : `Show ${isTable ? "column" : "series"}`
                }
                className="relative flex h-7 w-7 shrink-0 items-center justify-center text-[#657082] disabled:cursor-not-allowed disabled:opacity-45"
                disabled={required}
                title={required ? "Required by this view" : undefined}
                type="button"
                onClick={() => toggleVisibility(reference)}
              >
                {visible ? (
                  <Eye className="h-4 w-4" />
                ) : (
                  <EyeOff className="h-4 w-4" />
                )}
                {!isTable ? (
                  <span
                    className="absolute bottom-0 right-0 h-2 w-2 rounded-full border border-white"
                    style={{ backgroundColor: color }}
                  />
                ) : null}
              </button>
              <button
                className="min-w-0 flex-1 text-left"
                type="button"
                onClick={() => setActiveValueId(reference)}
              >
                <span className="block truncate text-sm font-semibold text-[#1f2937]">
                  {displayLabel(value, optionBySource)}
                </span>
                <span className="flex min-w-0 items-center gap-1.5 text-xs text-[#758195]">
                  <span className="truncate">
                    {roleForValue(draft.view, reference) ||
                      sourceLabel(value, option)}
                  </span>
                  {value.aggregation !== "raw" ? (
                    <Badge variant="outline">
                      {titleCase(value.aggregation)}
                    </Badge>
                  ) : null}
                  {value.filters.length ? (
                    <Badge variant="outline">
                      {value.filters.length} filters
                    </Badge>
                  ) : null}
                  {isContractValue(value) &&
                  isCustomScope(value, draft.analysis.grain) ? (
                    <Badge variant="outline">Custom results</Badge>
                  ) : null}
                  {option &&
                  !isInsightPickerOptionCompatible(
                    option,
                    draft.analysis.grain,
                  ) ? (
                    <Badge variant="destructive">
                      Unavailable for {titleCase(`${draft.analysis.grain}s`)}
                    </Badge>
                  ) : null}
                </span>
              </button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    aria-label={`${displayLabel(value, optionBySource)} actions`}
                    size="icon"
                    variant="ghost"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="min-w-[190px]">
                  <DropdownMenuItem onClick={() => setActiveValueId(reference)}>
                    <Settings2 className="h-4 w-4" /> Configure
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => duplicateValue(reference)}>
                    <Copy className="h-4 w-4" /> Duplicate
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    disabled={index === 0}
                    onClick={() => moveValue(reference, -1)}
                  >
                    <ChevronUp className="h-4 w-4" /> Move up
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    disabled={index === draft.analysis.values.length - 1}
                    onClick={() => moveValue(reference, 1)}
                  >
                    <ChevronDown className="h-4 w-4" /> Move down
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    className="text-[#b42318]"
                    onClick={() => removeIds(new Set([reference]))}
                  >
                    <Trash2 className="h-4 w-4" /> Remove
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          );
        })}
      </div>
      {!draft.analysis.values.length ? (
        <div className="rounded-lg border border-dashed border-[#cfd8e3] bg-[#f8fafc] px-4 py-6 text-center">
          <p className="m-0 text-sm font-semibold text-[#526071]">
            {isTable
              ? "Add columns to build this table."
              : "Choose the data to visualize."}
          </p>
          <p className="mb-0 mt-1 text-xs text-[#758195]">
            Results and project metadata can be used together.
          </p>
        </div>
      ) : null}
      {manage && managedIds.size ? (
        <Button
          className="w-full bg-[#b42318] text-white hover:bg-[#912018]"
          onClick={() => removeIds(managedIds)}
        >
          <Trash2 className="h-4 w-4" /> Remove {managedIds.size} selected
        </Button>
      ) : null}
      <InsightValuePicker
        grain={draft.analysis.grain}
        mode={isTable ? "multiple" : "single"}
        options={options}
        status={pickerStatus}
        onSelect={addOptions}
      >
        <Button className="w-auto" size="sm" variant="outline">
          <Plus className="h-4 w-4" /> {addLabel}
        </Button>
      </InsightValuePicker>
      {activeValue ? (
        <FieldSettingsDrawer
          draft={draft}
          option={activeOption}
          options={options}
          pickerStatus={pickerStatus}
          value={activeValue}
          onClose={() => setActiveValueId(null)}
          onEditScope={() => onEditScope(valueReference(activeValue))}
          onDraftChange={onChange}
          onReplace={(option) =>
            replaceValue(valueReference(activeValue), option)
          }
          onUpdate={(patch) => updateValue(valueReference(activeValue), patch)}
        />
      ) : null}
    </section>
  );
}

function FieldSettingsDrawer({
  draft,
  option,
  options,
  pickerStatus,
  value,
  onClose,
  onEditScope,
  onDraftChange,
  onReplace,
  onUpdate,
}: {
  draft: InsightDraft;
  option?: InsightPickerOption;
  options: InsightPickerOption[];
  pickerStatus: "loading" | "error" | "ready";
  value: AnalysisValue;
  onClose: () => void;
  onEditScope: () => void;
  onDraftChange: (draft: InsightDraft) => void;
  onReplace: (option: InsightPickerOption) => void;
  onUpdate: (patch: Partial<AnalysisValue>) => void;
}) {
  const aggregations = Array.from(
    new Set([value.aggregation, ...(option?.allowedAggregations ?? ["raw"])]),
  );
  return (
    <div
      className="fixed inset-0 z-[70] flex justify-end bg-black/20"
      onClick={onClose}
    >
      <aside
        aria-label="Field settings"
        className="h-full w-[min(420px,94vw)] overflow-y-auto border-l border-[#d6dee8] bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#dce3eb] bg-white px-4 py-3">
          <div>
            <div className="text-sm font-semibold text-[#1f2937]">
              Field settings
            </div>
            <div className="text-xs text-[#657082]">
              {option?.label ?? titleCase(value.field)}
            </div>
          </div>
          <Button
            aria-label="Close field settings"
            size="icon"
            variant="ghost"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="space-y-5 p-4">
          <DrawerSection title="Field">
            <InsightValuePicker
              grain={draft.analysis.grain}
              options={options}
              status={pickerStatus}
              selectedKey={sourceKey(value)}
              onSelect={(selected) => selected[0] && onReplace(selected[0])}
            >
              <Button className="w-full justify-between" variant="outline">
                <span className="truncate">
                  {option?.label ?? titleCase(value.field)}
                </span>
                <span className="text-xs text-[#657082]">Replace</span>
              </Button>
            </InsightValuePicker>
          </DrawerSection>
          <DrawerSection title="Display label">
            <Input
              placeholder={option?.label ?? titleCase(value.field)}
              value={value.label ?? ""}
              onChange={(event) =>
                onUpdate({ label: event.target.value || undefined })
              }
            />
          </DrawerSection>
          <DrawerSection title="Aggregation">
            <Select
              value={value.aggregation}
              onValueChange={(aggregation: AnalysisValue["aggregation"]) =>
                onUpdate({ aggregation })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {aggregations.map((aggregation) => (
                  <SelectItem key={aggregation} value={aggregation}>
                    {titleCase(aggregation)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </DrawerSection>
          <DrawerSection title="Filters">
            <div className="space-y-2">
              {value.filters.map((filter, index) => (
                <div
                  className="grid grid-cols-[120px_minmax(0,1fr)_32px] gap-1.5"
                  key={`${filter.operator}-${index}`}
                >
                  <Select
                    value={filter.operator}
                    onValueChange={(
                      operator: AnalysisValue["filters"][number]["operator"],
                    ) => {
                      const filters = value.filters.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, operator } : item,
                      );
                      onUpdate({ filters });
                    }}
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {[
                        "eq",
                        "ne",
                        "gt",
                        "gte",
                        "lt",
                        "lte",
                        "in",
                        "not_in",
                        "contains",
                      ].map((operator) => (
                        <SelectItem key={operator} value={operator}>
                          {titleCase(operator)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    className="h-9"
                    placeholder="Value"
                    value={filterValueText(filter.value)}
                    onChange={(event) => {
                      const filters = value.filters.map((item, itemIndex) =>
                        itemIndex === index
                          ? {
                              ...item,
                              value: parseFilterValue(
                                event.target.value,
                                item.operator,
                                option?.valueType,
                              ),
                            }
                          : item,
                      );
                      onUpdate({ filters });
                    }}
                  />
                  <Button
                    aria-label="Remove filter"
                    className="h-9 w-8"
                    size="icon"
                    variant="ghost"
                    onClick={() =>
                      onUpdate({
                        filters: value.filters.filter(
                          (_, itemIndex) => itemIndex !== index,
                        ),
                      })
                    }
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  onUpdate({
                    filters: [
                      ...value.filters,
                      {
                        field: sourceFieldId(value),
                        operator: "eq",
                        value: "",
                      },
                    ],
                  })
                }
              >
                <Plus className="h-4 w-4" /> Add filter
              </Button>
            </div>
          </DrawerSection>
          {isContractValue(value) ? (
            <DrawerSection title="Results from">
              <Button
                className="w-full justify-between"
                variant="outline"
                onClick={onEditScope}
              >
                <span>
                  {titleCase(
                    value.scope?.selection ?? "latest_successful_per_sample",
                  )}
                </span>
                <Settings2 className="h-4 w-4" />
              </Button>
              <p className="m-0 text-xs text-[#657082]">
                The default automatically resolves the appropriate result for
                each {draft.analysis.grain}.
              </p>
            </DrawerSection>
          ) : null}
          {hasRecordColors(draft.view) ? (
            <DrawerSection title="Color">
              <label className="flex items-center gap-3 rounded-md border border-[#dce3eb] px-3 py-2">
                <input
                  className="h-8 w-10 cursor-pointer border-0 bg-transparent p-0"
                  type="color"
                  value={colorForValue(
                    draft.view,
                    valueReference(value),
                    draft.analysis.values.indexOf(value),
                  )}
                  onChange={(event) =>
                    setValueColor(
                      draft,
                      valueReference(value),
                      event.target.value,
                      onDraftChange,
                    )
                  }
                />
                <span className="text-sm text-[#526071]">Series color</span>
              </label>
            </DrawerSection>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

// view bindings is responsible for rendering the binding grid for the current view type
function ViewBindings({
  draft,
  onChange,
}: {
  draft: InsightDraft;
  onChange: (draft: InsightDraft) => void;
}) {
  const options = draft.analysis.values;
  if (!options.length) return null;

  if (draft.view.kind === "scatter") {
    const view = draft.view;
    return (
      <BindingGrid title="Plot fields">
        <ValueBinding
          label="X axis"
          value={view.x}
          values={options}
          onChange={(x) =>
            onChange({ ...draft, view: bindRequiredValue(view, "x", x) })
          }
        />
        <ValueBinding
          label="Y axis"
          value={view.y}
          values={options}
          onChange={(y) =>
            onChange({ ...draft, view: bindRequiredValue(view, "y", y) })
          }
        />
      </BindingGrid>
    );
  }

  if (draft.view.kind === "metric") {
    const view = draft.view;
    return (
      <BindingGrid title="Metric field">
        <ValueBinding
          label="Value"
          value={view.value}
          values={options}
          onChange={(value) =>
            onChange({
              ...draft,
              view: bindRequiredValue(view, "value", value),
            })
          }
        />
      </BindingGrid>
    );
  }

  if (draft.view.kind === "heatmap") {
    const view = draft.view;
    return (
      <BindingGrid title="Heatmap fields">
        <ValueBinding
          label="X"
          value={view.x}
          values={options}
          onChange={(x) =>
            onChange({ ...draft, view: bindRequiredValue(view, "x", x) })
          }
        />
        <ValueBinding
          label="Y"
          value={view.y}
          values={options}
          onChange={(y) =>
            onChange({ ...draft, view: bindRequiredValue(view, "y", y) })
          }
        />
        <ValueBinding
          label="Value"
          value={view.value}
          values={options}
          onChange={(value) =>
            onChange({
              ...draft,
              view: bindRequiredValue(view, "value", value),
            })
          }
        />
      </BindingGrid>
    );
  }

  if (hasCategoryBinding(draft.view)) {
    const view = draft.view;
    return (
      <BindingGrid title="Category">
        <div className="space-y-1">
          <Label className="text-xs">Group or label by</Label>
          <Select
            value={view.category ?? "__identity__"}
            onValueChange={(category) =>
              onChange({
                ...draft,
                view: bindCategoryValue(
                  view,
                  category === "__identity__" ? undefined : category,
                  options,
                ),
              })
            }
          >
            <SelectTrigger className="h-9">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__identity__">
                {titleCase(draft.analysis.grain)} identity
              </SelectItem>
              {options.map((value) => {
                const reference = valueReference(value);
                return (
                  <SelectItem key={reference} value={reference}>
                    {value.label || titleCase(value.field)}
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>
        </div>
      </BindingGrid>
    );
  }
  return null;
}

function ValueBinding({
  label,
  value,
  values,
  onChange,
}: {
  label: string;
  value: string;
  values: AnalysisValue[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger aria-label={label} className="h-9">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {values.map((item) => {
            const reference = valueReference(item);
            return (
              <SelectItem key={reference} value={reference}>
                {item.label || titleCase(item.field)}
              </SelectItem>
            );
          })}
        </SelectContent>
      </Select>
    </div>
  );
}

function BindingGrid({
  children,
  title,
}: {
  children: ReactNode;
  title: string;
}) {
  return (
    <div className="space-y-2 rounded-lg border border-[#dce3eb] bg-[#f8fafc] p-3">
      <h2 className="m-0 text-xs font-bold uppercase tracking-wide text-[#526071]">
        {title}
      </h2>
      <div className="grid gap-2 sm:grid-cols-2">{children}</div>
    </div>
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

function sourceKey(value: Pick<AnalysisValue, "field">) {
  return value.field;
}

function displayLabel(
  value: AnalysisValue,
  options: Map<string, InsightPickerOption>,
) {
  return (
    value.label ||
    options.get(sourceKey(value))?.label ||
    titleCase(value.field)
  );
}

function sourceLabel(value: AnalysisValue, option?: InsightPickerOption) {
  return isContractValue(value)
    ? (option?.groupLabel ?? "Results")
    : (option?.groupLabel ?? "Metadata");
}

function sourceFieldId(value: Pick<AnalysisValue, "field">) {
  return parseFieldReference(value.field).fieldId;
}

function isContractValue(value: Pick<AnalysisValue, "field">) {
  return parseFieldReference(value.field).kind === "contract";
}

function roleForValue(view: InsightView, id: string) {
  if (view.hidden_values.includes(id))
    return view.kind === "table" ? "Hidden column" : "Hidden series";
  if (view.kind === "table") return "";
  if (view.kind === "scatter")
    return view.x === id
      ? "X axis"
      : view.y === id
        ? "Y axis"
        : "Available field";
  if (view.kind === "metric")
    return view.value === id ? "Metric value" : "Available field";
  if (view.kind === "heatmap") {
    if (view.x === id) return "X axis";
    if (view.y === id) return "Y axis";
    if (view.value === id) return "Cell value";
    return "Available field";
  }
  if ("category" in view && view.category === id) return "Category";
  if (view.kind === "histogram") return "Distribution";
  if (hasCategoryBinding(view)) return "Series";
  return "Available field";
}

function bindRequiredValue<
  View extends Extract<InsightView, { kind: "scatter" | "metric" | "heatmap" }>,
  Key extends Extract<keyof View, "x" | "y" | "value">,
>(view: View, key: Key, value: string): View {
  return {
    ...view,
    [key]: value,
    hidden_values: view.hidden_values.filter((id) => id !== value),
  } as View;
}

function bindCategoryValue(
  view: CategoryBindingView,
  category: string | undefined,
  values: AnalysisValue[],
): CategoryBindingView {
  const hidden = new Set(view.hidden_values.filter((id) => id !== category));
  if (view.kind === "pie" || view.kind === "donut") {
    const candidates = values
      .map(valueReference)
      .filter((id) => id !== category);
    const visible = candidates.filter((id) => !hidden.has(id));
    if (!visible.length && candidates[0]) hidden.delete(candidates[0]);
    const keptVisible = candidates.find((id) => !hidden.has(id));
    for (const id of candidates) {
      if (id !== keptVisible) hidden.add(id);
    }
  }
  return {
    ...view,
    category,
    hidden_values: values.map(valueReference).filter((id) => hidden.has(id)),
  };
}

function isCustomScope(value: AnalysisValue, grain: string) {
  const selection = value.scope?.selection;
  return (
    selection !== undefined &&
    selection !==
      (grain === "run" ? "all_eligible" : "latest_successful_per_sample")
  );
}

function colorForValue(view: InsightView, id: string, index: number) {
  if (hasRecordColors(view))
    return view.colors[id] ?? CHART_COLORS[index % CHART_COLORS.length];
  return CHART_COLORS[index % CHART_COLORS.length];
}

function setValueColor(
  draft: InsightDraft,
  id: string,
  color: string,
  onChange: (draft: InsightDraft) => void,
) {
  if (!hasRecordColors(draft.view)) return;
  onChange({
    ...draft,
    view: { ...draft.view, colors: { ...draft.view.colors, [id]: color } },
  });
}

function filterValueText(value: unknown) {
  if (Array.isArray(value)) return value.join(", ");
  if (value === null || value === undefined) return "";
  return String(value);
}

function parseFilterValue(
  value: string,
  operator: string,
  valueType?: string,
): unknown {
  if (operator === "in" || operator === "not_in") {
    return value.split(",").map((item) => parseScalar(item.trim(), valueType));
  }
  return parseScalar(value, valueType);
}

function parseScalar(value: string, valueType?: string): string | number {
  if (valueType === "numeric" && value.trim() && Number.isFinite(Number(value)))
    return Number(value);
  return value;
}
