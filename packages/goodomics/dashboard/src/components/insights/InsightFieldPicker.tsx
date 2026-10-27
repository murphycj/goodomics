import { Check, Database, Search } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import type { FieldSelection } from "../../lib/insightSchemas";
import { titleCase } from "../../lib/insightBuilder";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Input,
} from "../ui";

export type CatalogField = {
  field: string;
  field_id?: string;
  display_name: string;
  scalar_type: string;
  semantic_type?: string | null;
  description?: string | null;
  source: "contract" | "metadata";
  data_contract_id?: string;
  domain_tags?: string[];
};

type PickerTab = "all" | "results" | "metadata";

export function InsightFieldPicker({
  button,
  datasetNames,
  disabled,
  fields,
  mode = "single",
  onSelect,
  selected = [],
  title = mode === "multiple" ? "Add fields" : "Choose a field",
}: {
  button: ReactNode | ((open: () => void) => ReactNode);
  datasetNames: Record<string, string>;
  disabled?: boolean;
  fields: CatalogField[];
  mode?: "single" | "multiple";
  onSelect: (fields: CatalogField[]) => void;
  selected?: string[];
  title?: string;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<PickerTab>("all");
  const [pending, setPending] = useState<Set<string>>(new Set());
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const visible = useMemo(
    () => filterFields(fields, tab, search),
    [fields, search, tab],
  );
  const groups = useMemo(
    () => groupFields(visible, datasetNames),
    [datasetNames, visible],
  );

  const choose = (field: CatalogField) => {
    if (mode === "single") {
      onSelect([field]);
      setOpen(false);
      return;
    }
    setPending((current) => {
      const next = new Set(current);
      if (next.has(field.field)) next.delete(field.field);
      else next.add(field.field);
      return next;
    });
  };

  return (
    <>
      {typeof button === "function" ? button(() => !disabled && setOpen(true)) : (
        <span
          className={disabled ? "pointer-events-none opacity-50" : "contents"}
          onClick={() => !disabled && setOpen(true)}
        >
          {button}
        </span>
      )}
      <Dialog
        open={open}
        onOpenChange={(value) => {
          setOpen(value);
          if (!value) setPending(new Set());
        }}
      >
        <DialogContent className="flex max-h-[84vh] max-w-[820px] flex-col gap-0 overflow-hidden p-0">
          <DialogHeader className="border-b border-[#dce3eb] px-5 py-4 pr-16">
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>
              Fields are grouped by their data contract so their analytical context stays visible.
            </DialogDescription>
          </DialogHeader>
          <div className="shrink-0 px-5 pt-4">
            <div className="relative">
              <Search className="absolute left-3 top-3 h-4 w-4 text-[#758195]" />
              <Input
                autoFocus
                className="h-10 pl-9"
                placeholder="Search fields, contracts, or types…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
            <div className="mt-3 flex gap-7 border-b border-[#dce3eb]">
              {(["all", "results", "metadata"] as const).map((item) => (
                <button
                  className={[
                    "border-b-2 px-1 pb-2 text-sm font-medium capitalize",
                    tab === item ? "border-[#16784a] text-[#16784a]" : "border-transparent text-[#657082] hover:text-[#253343]",
                  ].join(" ")}
                  key={item}
                  type="button"
                  onClick={() => setTab(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-5 py-4">
            {groups.map((group) => (
              <section className="overflow-hidden rounded-lg border border-[#d6dee8] bg-white [content-visibility:auto]" key={group.key}>
                <div className="flex items-center gap-2 border-b border-[#e8edf3] px-3 py-2.5">
                  <Database className="h-4 w-4 text-[#657082]" />
                  <div className="min-w-0 flex-1 truncate text-xs font-bold uppercase tracking-wide text-[#526071]">{group.label}</div>
                  <span className="text-xs text-[#758195]">{group.fields.length} fields</span>
                  {mode === "multiple" ? (
                    <button
                      className="text-sm font-medium text-[#16784a] hover:underline"
                      type="button"
                      onClick={() => setPending((current) => new Set([...current, ...group.fields.map((field) => field.field)]))}
                    >
                      Add all
                    </button>
                  ) : null}
                </div>
                <div className="grid gap-0.5 p-1.5">
                  {group.fields.map((field) => {
                    const checked = pending.has(field.field) || (mode === "single" && selectedSet.has(field.field));
                    return (
                      <button
                        className={[
                          "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-md px-2.5 py-2.5 text-left transition-colors",
                          checked ? "bg-[#f0f7f3]" : "hover:bg-[#f6f8fa]",
                        ].join(" ")}
                        key={field.field}
                        type="button"
                        onClick={() => choose(field)}
                      >
                        <span className="min-w-0">
                          <span className="flex items-center gap-2">
                            {mode === "multiple" ? <SelectionBox checked={checked} /> : null}
                            <span className="truncate text-sm font-semibold text-[#1f2937]">{field.display_name}</span>
                          </span>
                          <span className={[
                            "mt-0.5 block truncate font-mono text-[11px] text-[#758195]",
                            mode === "multiple" ? "pl-6" : "",
                          ].join(" ")}>{field.field_id || field.field}</span>
                        </span>
                        <span className="rounded bg-[#eef3f7] px-2 py-1 text-xs text-[#526071]">{titleCase(field.scalar_type)}</span>
                      </button>
                    );
                  })}
                </div>
              </section>
            ))}
            {!groups.length ? (
              <div className="rounded-lg border border-dashed border-[#cfd8e3] p-8 text-center text-sm text-[#657082]">No fields match this search.</div>
            ) : null}
          </div>
          <div className="flex shrink-0 items-center justify-between border-t border-[#dce3eb] bg-white px-5 py-3">
            <span className="text-sm text-[#657082]">
              {mode === "multiple" ? `${pending.size} field${pending.size === 1 ? "" : "s"} selected` : "Choose one field"}
            </span>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
              {mode === "multiple" ? (
                <Button
                  disabled={!pending.size}
                  onClick={() => {
                    onSelect(fields.filter((field) => pending.has(field.field)));
                    setOpen(false);
                    setPending(new Set());
                  }}
                >
                  Add fields
                </Button>
              ) : null}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function catalogSelection(field: CatalogField, current?: FieldSelection): FieldSelection {
  return {
    ...current,
    field: field.field,
    ...(current?.label ? {} : { label: field.display_name }),
  };
}

function SelectionBox({ checked }: { checked: boolean }) {
  return (
    <span className={[
      "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
      checked ? "border-[#16784a] bg-[#16784a] text-white" : "border-[#b8c2cf] bg-white",
    ].join(" ")}>
      {checked ? <Check className="h-3 w-3" /> : null}
    </span>
  );
}

function filterFields(fields: CatalogField[], tab: PickerTab, search: string) {
  const term = search.trim().toLowerCase();
  return fields.filter((field) => {
    if (tab === "results" && field.source !== "contract") return false;
    if (tab === "metadata" && field.source !== "metadata") return false;
    if (!term) return true;
    return [field.display_name, field.field, field.field_id, field.scalar_type, field.semantic_type, field.data_contract_id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(term));
  });
}

function groupFields(fields: CatalogField[], datasetNames: Record<string, string>) {
  const groups = new Map<string, { key: string; label: string; fields: CatalogField[] }>();
  for (const field of fields) {
    const metadataEntity = field.field.startsWith("metadata/") ? field.field.split("/")[1] : null;
    const groupId = field.source === "metadata" ? `metadata:${metadataEntity || "project"}` : `contract:${field.data_contract_id || "results"}`;
    const label = field.source === "metadata"
      ? `${titleCase(metadataEntity || "Project")} metadata`
      : datasetNames[field.data_contract_id || ""] || titleCase(field.data_contract_id || "Results");
    const group = groups.get(groupId) ?? { key: groupId, label, fields: [] };
    group.fields.push(field);
    groups.set(groupId, group);
  }
  return [...groups.values()].sort((left, right) => left.label.localeCompare(right.label));
}
