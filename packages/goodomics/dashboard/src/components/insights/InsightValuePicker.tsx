import { Check, ChevronDown, Database, Search } from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent,
  type ReactNode,
} from "react";
import type { DataContract } from "../../api";
import type { AnalysisValue, InsightDraft } from "../../lib/insightSchemas";
import { titleCase } from "../../lib/insightBuilder";
import {
  contractFieldReference,
  parseFieldReference,
} from "../../lib/fieldReferences";
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
  Input,
} from "../ui";

export type InsightPickerOption = {
  key: string;
  source: "results" | "metadata";
  groupId: string;
  groupLabel: string;
  label: string;
  fieldId: string;
  valueType: string;
  description?: string;
  allowedAggregations: AnalysisValue["aggregation"][];
  allowedGrains?: string[];
  value: AnalysisValue;
};

type PickerTab = "all" | "results" | "metadata";

export function buildInsightPickerOptions(
  contracts: DataContract[],
  metadataFields: Record<string, unknown>[],
  aggregationsByType: Record<string, string[]>,
  resultScope: AnalysisValue["scope"],
): InsightPickerOption[] {
  const contractOptions: InsightPickerOption[] = contracts.flatMap((contract) =>
    contract.fields.map((field) => {
      const fieldReference = contractFieldReference(
        contract.data_contract_id,
        field.field_id,
      );
      return {
        key: fieldReference,
        source: "results" as const,
        groupId: contract.data_contract_id,
        groupLabel: contract.name,
        label: field.display_name || titleCase(field.field_id),
        fieldId: field.field_id,
        valueType: field.value_type || "string",
        description: field.description ?? undefined,
        allowedAggregations: aggregationOptions(
          aggregationsByType[field.value_type],
        ),
        value: {
          field: fieldReference,
          aggregation: "raw" as const,
          filters: [],
          scope: resultScope,
        },
      };
    }),
  );
  const metadataOptions: InsightPickerOption[] = metadataFields.flatMap((field) => {
    const entity = typeof field.entity === "string" ? field.entity : "";
    const fieldReference = typeof field.field === "string" ? field.field : "";
    let fieldId = "";
    try {
      const parsed = parseFieldReference(fieldReference);
      if (parsed.kind !== "metadata" || parsed.entity !== entity) return [];
      fieldId = parsed.fieldId;
    } catch {
      return [];
    }
    if (!("subject sample run file".split(" ").includes(entity))) {
      return [];
    }
    const allowedGrains = stringArray(field.allowed_grains);
    return [
      {
        key: fieldReference,
        source: "metadata" as const,
        groupId: entity,
        groupLabel: `${titleCase(entity)}s`,
        label: String(field.label ?? titleCase(fieldId)),
        fieldId,
        valueType: String(field.value_type ?? "string"),
        description: undefined,
        allowedAggregations: aggregationOptions(
          stringArray(field.allowed_aggregations),
        ),
        allowedGrains,
        value: {
          field: fieldReference,
          aggregation: "raw" as const,
          filters: [],
        },
      },
    ];
  });
  return [...contractOptions, ...metadataOptions];
}

export function InsightValuePicker({
  children,
  grain,
  mode = "single",
  options,
  status = "ready",
  selectedKey,
  onSelect,
}: {
  children?: ReactNode;
  grain: InsightDraft["analysis"]["grain"];
  mode?: "single" | "multiple";
  options: InsightPickerOption[];
  status?: "loading" | "error" | "ready";
  selectedKey?: string;
  onSelect: (options: InsightPickerOption[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<PickerTab>("all");
  const [search, setSearch] = useState("");
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const visible = useMemo(
    () => filterOptions(options, tab, search, grain),
    [grain, options, search, tab],
  );
  const groups = useMemo(() => groupOptions(visible), [visible]);
  const visibleIndexByKey = useMemo(
    () => new Map(visible.map((option, index) => [option.key, index])),
    [visible],
  );

  useEffect(() => {
    if (!open) return;
    setPending(new Set());
    const frame = window.requestAnimationFrame(() => inputRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  useEffect(() => setActiveIndex(0), [search, tab]);

  const choose = (option: InsightPickerOption) => {
    if (!isInsightPickerOptionCompatible(option, grain)) return;
    if (mode === "single") {
      onSelect([option]);
      setOpen(false);
      return;
    }
    setPending((current) => {
      const next = new Set(current);
      if (next.has(option.key)) next.delete(option.key);
      else next.add(option.key);
      return next;
    });
  };

  const chooseTab = (item: PickerTab) => setTab(item);

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!visible.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % visible.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => (current - 1 + visible.length) % visible.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      const option = visible[activeIndex];
      if (option) choose(option);
    }
  };

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        {children ?? (
          <Button className="w-full justify-between" variant="outline">
            Choose fields <ChevronDown className="h-4 w-4" />
          </Button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        side="right"
        sideOffset={8}
        className="z-[90] max-h-[calc(100vh-24px)] w-[min(620px,calc(100vw-32px))] p-0"
        onCloseAutoFocus={(event) => event.preventDefault()}
      >
        <div className="bg-white px-3 pt-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#758195]" />
            <Input
              ref={inputRef}
              className="h-10 pl-9"
              placeholder="Search fields…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>
          <div aria-label="Field source" className="mt-3 flex gap-5 border-b border-[#e2e8f0]" role="tablist">
            {(["all", "results", "metadata"] as const).map((item) => (
              <button
                aria-selected={tab === item}
                className={[
                  "-mb-px border-b-2 px-1 pb-2 text-sm font-semibold transition-colors",
                  tab === item
                    ? "border-[#16784a] text-[#16784a]"
                    : "border-transparent text-[#657082] hover:text-[#1f2937]",
                ].join(" ")}
                data-picker-tab={item}
                key={item}
                role="tab"
                type="button"
                onClick={(event: MouseEvent<HTMLButtonElement>) => {
                  event.preventDefault();
                  if (event.detail === 0) chooseTab(item);
                }}
                onPointerDown={(event: PointerEvent<HTMLButtonElement>) => {
                  event.preventDefault();
                  event.stopPropagation();
                  chooseTab(item);
                }}
              >
                {titleCase(item)}
              </button>
            ))}
          </div>
        </div>
        <div className="max-h-[min(430px,calc(100vh-190px))] space-y-3 overflow-y-auto bg-[#f8fafc] p-3">
          {status === "loading" ? (
            <PickerMessage>Loading available fields…</PickerMessage>
          ) : status === "error" ? (
            <PickerMessage>Available fields could not be loaded. Try reopening the picker.</PickerMessage>
          ) : null}
          {status === "ready" ? groups.map((group) => (
            <section
              className="overflow-hidden rounded-lg border border-[#d9e1ea] bg-white"
              key={`${group.source}:${group.id}`}
            >
              <div className="flex items-center gap-2 border-b border-[#e8edf3] px-3 py-2">
                <Database className="h-4 w-4 text-[#657082]" />
                <div className="min-w-0 flex-1 truncate text-xs font-bold uppercase tracking-wide text-[#526071]">
                  {group.label}
                </div>
                <span className="text-xs text-[#758195]">{group.options.length} fields</span>
                {mode === "multiple" ? (
                  <button
                    className="text-xs font-semibold text-[#16784a] hover:underline"
                    type="button"
                    onClick={() =>
                      setPending((current) => {
                        const next = new Set(current);
                        for (const option of group.options) {
                          if (isInsightPickerOptionCompatible(option, grain)) next.add(option.key);
                        }
                        return next;
                      })
                    }
                  >
                    Add all
                  </button>
                ) : null}
              </div>
              <div className="grid gap-0.5 p-1.5">
                {group.options.map((option) => {
                  const index = visibleIndexByKey.get(option.key) ?? -1;
                  const checked = pending.has(option.key) || selectedKey === option.key;
                  return (
                    <button
                      className={[
                        "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-md px-2.5 py-2 text-left transition-colors",
                        index === activeIndex
                          ? "bg-[#f0f7f3]"
                          : "hover:bg-[#f6f8fa]",
                      ].join(" ")}
                      key={option.key}
                      type="button"
                      onClick={() => choose(option)}
                      onMouseEnter={() => setActiveIndex(index)}
                    >
                      <span className="min-w-0">
                        <span className="flex items-center gap-2">
                          {mode === "multiple" ? (
                            <span
                              className={[
                                "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                                checked
                                  ? "border-[#16784a] bg-[#16784a] text-white"
                                  : "border-[#b8c2cf] bg-white",
                              ].join(" ")}
                            >
                              {checked ? <Check className="h-3 w-3" /> : null}
                            </span>
                          ) : null}
                          <span className="truncate text-sm font-semibold text-[#1f2937]">
                            {option.label}
                          </span>
                        </span>
                        <span className="mt-0.5 block truncate pl-6 text-xs text-[#758195]">
                          {option.description || option.fieldId}
                        </span>
                      </span>
                      <span className="rounded bg-[#eef3f7] px-2 py-1 text-xs text-[#526071]">
                        {titleCase(option.valueType)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>
          )) : null}
          {status === "ready" && !groups.length ? (
            <PickerMessage>{emptyPickerMessage(tab, search, grain)}</PickerMessage>
          ) : null}
        </div>
        {mode === "multiple" ? (
          <div className="flex items-center justify-between border-t border-[#e2e8f0] bg-white px-3 py-2.5">
            <span className="text-xs text-[#657082]">
              {pending.size} field{pending.size === 1 ? "" : "s"} selected
            </span>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                disabled={!pending.size}
                onClick={() => {
                  onSelect(options.filter((option) => pending.has(option.key)));
                  setOpen(false);
                }}
              >
                Add fields
              </Button>
            </div>
          </div>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function filterOptions(
  options: InsightPickerOption[],
  tab: PickerTab,
  search: string,
  grain: InsightDraft["analysis"]["grain"],
) {
  const query = search.trim().toLowerCase();
  return options.filter((option) => {
    if (!isInsightPickerOptionCompatible(option, grain)) return false;
    if (tab !== "all" && option.source !== tab) return false;
    if (!query) return true;
    return [option.label, option.fieldId, option.groupLabel, option.description]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query));
  });
}

function groupOptions(options: InsightPickerOption[]) {
  const groups = new Map<
    string,
    { id: string; label: string; source: InsightPickerOption["source"]; options: InsightPickerOption[] }
  >();
  for (const option of options) {
    const key = `${option.source}:${option.groupId}`;
    const group = groups.get(key) ?? {
      id: option.groupId,
      label: option.groupLabel,
      source: option.source,
      options: [],
    };
    group.options.push(option);
    groups.set(key, group);
  }
  return [...groups.values()];
}

export function isInsightPickerOptionCompatible(option: InsightPickerOption, grain: string) {
  return !option.allowedGrains?.length || option.allowedGrains.includes(grain);
}

function emptyPickerMessage(
  tab: PickerTab,
  search: string,
  grain: InsightDraft["analysis"]["grain"],
) {
  if (search.trim()) return "No fields match this search.";
  if (tab === "metadata") return `No metadata fields are available for ${titleCase(`${grain}s`)}.`;
  if (tab === "results") return "No result fields are available.";
  return `No fields are available for ${titleCase(`${grain}s`)}.`;
}

function stringArray(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function aggregationOptions(values: string[] | undefined) {
  const allowed = new Set([
    "raw",
    "count",
    "count_distinct",
    "sum",
    "avg",
    "min",
    "max",
  ]);
  const options = (values ?? []).filter(
    (value): value is AnalysisValue["aggregation"] => allowed.has(value),
  );
  return options.length ? options : (["raw"] as AnalysisValue["aggregation"][]);
}

function PickerMessage({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-[#cfd8e3] bg-white p-6 text-center text-sm text-[#657082]">
      {children}
    </div>
  );
}
