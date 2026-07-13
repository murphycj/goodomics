import { SlidersHorizontal } from "lucide-react";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { getContractResultOptions, type DataContract } from "../../api";
import {
  Button,
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui";

export type ResultScope = {
  selection:
    | "latest_successful_per_sample"
    | "specific_methods"
    | "specific_versions"
    | "specific_runs"
    | "pinned_results";
  analysisTypeIds: string[];
  methodIds: string[];
  methodVersions: string[];
  runIds: string[];
  statuses: string[];
  startedAfter: string;
  endedBefore: string;
  runContractIds: string[];
};

export const defaultResultScope = (): ResultScope => ({
  selection: "latest_successful_per_sample",
  analysisTypeIds: [],
  methodIds: [],
  methodVersions: [],
  runIds: [],
  statuses: [],
  startedAfter: "",
  endedBefore: "",
  runContractIds: [],
});

export function ResultScopeEditor({
  contract,
  projectId,
  open,
  scope,
  onOpenChange,
  onChange,
}: {
  contract: DataContract | undefined;
  projectId: string;
  open: boolean;
  scope: ResultScope;
  onOpenChange: (open: boolean) => void;
  onChange: (scope: ResultScope) => void;
}) {
  const update = (patch: Partial<ResultScope>) => onChange({ ...scope, ...patch });
  const options = useQuery({
    queryKey: ["contract-result-options", projectId, contract?.data_contract_id],
    queryFn: () => getContractResultOptions(projectId, contract!.data_contract_id),
    enabled: open && Boolean(contract?.data_contract_id),
    staleTime: 30_000,
  });
  const analysisTypes = scope.analysisTypeIds.length
    ? scope.analysisTypeIds
    : contract?.compatible_analysis_type_ids ?? [];
  const summary = [
    selectionLabel(scope.selection),
    analysisTypes.length ? analysisTypes.map(readableId).join(", ") : "Compatible types",
    scope.methodIds.length ? scope.methodIds.join(", ") : "Compatible methods",
    scope.methodVersions.length
      ? `${scope.methodVersions.length} method version${scope.methodVersions.length === 1 ? "" : "s"}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <Button
        aria-label={`Results from ${summary}`}
        className="h-auto w-full justify-between gap-2 rounded-md border border-[#dce3eb] bg-[#f8fafc] px-3 py-2 text-left font-normal hover:bg-[#f1f5f9]"
        type="button"
        variant="outline"
        onClick={() => onOpenChange(true)}
      >
        <span className="min-w-0">
          <span className="block text-[11px] font-semibold uppercase tracking-wide text-[#64748b]">
            Results from
          </span>
          <span className="block truncate text-xs text-[#334155]">{summary}</span>
        </span>
        <SlidersHorizontal className="h-4 w-4 shrink-0 text-[#64748b]" />
      </Button>
      <DialogContent className="flex h-[min(760px,92vh)] max-h-[92vh] max-w-[min(900px,94vw)] flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="shrink-0 border-b border-[#dce3eb] px-6 py-5 pr-16">
          <DialogTitle className="text-lg">Results from</DialogTitle>
          <p className="text-sm text-[#64748b]">
            Choose which compatible results supply this data series. Blank filters use the data contract defaults.
          </p>
          <p className="truncate pt-1 text-xs font-medium text-[#475569]">{summary}</p>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <div className="grid gap-x-5 gap-y-4 md:grid-cols-2">
          <ScopeField label="Selection">
            <Select
              value={scope.selection}
              onValueChange={(selection) =>
                update({ selection: selection as ResultScope["selection"] })
              }
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="latest_successful_per_sample">Latest successful per sample</SelectItem>
                <SelectItem value="specific_methods">Specific methods</SelectItem>
                <SelectItem value="specific_versions">Specific versions</SelectItem>
                <SelectItem value="specific_runs">Specific runs</SelectItem>
                <SelectItem value="pinned_results">Pinned results</SelectItem>
              </SelectContent>
            </Select>
          </ScopeField>
          {options.isError ? (
            <div className="sm:col-span-2 rounded-md border border-[#fecaca] bg-[#fff1f2] p-2 text-xs text-[#b42318]">
              Result options could not be loaded.
            </div>
          ) : null}
          <CsvField label="Analysis types" suggestions={(options.data?.analysis_types ?? []).map((item) => item.id)} value={scope.analysisTypeIds} onChange={(analysisTypeIds) => update({ analysisTypeIds })} />
          <CsvField label="Methods" suggestions={(options.data?.methods ?? []).map((item) => item.id)} value={scope.methodIds} onChange={(methodIds) => update({ methodIds })} />
          <CsvField label="Method versions" suggestions={options.data?.method_versions} value={scope.methodVersions} onChange={(methodVersions) => update({ methodVersions })} />
          <CsvField label="Exact runs" suggestions={(options.data?.runs ?? []).map((item) => item.id)} value={scope.runIds} onChange={(runIds) => update({ runIds })} />
          <CsvField label="Statuses" suggestions={options.data?.statuses} value={scope.statuses} onChange={(statuses) => update({ statuses })} />
          <ScopeField label="Started after">
            <Input type="datetime-local" value={scope.startedAfter} onChange={(event) => update({ startedAfter: event.target.value })} />
          </ScopeField>
          <ScopeField label="Ended before">
            <Input type="datetime-local" value={scope.endedBefore} onChange={(event) => update({ endedBefore: event.target.value })} />
          </ScopeField>
          <div className="sm:col-span-2">
            <CsvField label="Pinned run-contract IDs" value={scope.runContractIds} onChange={(runContractIds) => update({ runContractIds })} />
          </div>
          </div>
        </div>
        <DialogFooter className="shrink-0 border-t border-[#dce3eb] bg-[#f8fafc] px-6 py-4">
          <Button type="button" variant="ghost" onClick={() => onChange(defaultResultScope())}>
            Reset to compatible defaults
          </Button>
          <DialogClose asChild>
            <Button type="button">Done</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CsvField({ label, suggestions = [], value, onChange }: { label: string; suggestions?: string[]; value: string[]; onChange: (value: string[]) => void }) {
  return (
    <ScopeField label={label}>
      <Input
        placeholder="Comma-separated; blank uses contract compatibility"
        value={value.join(", ")}
        onChange={(event) =>
          onChange(event.target.value.split(",").map((item) => item.trim()).filter(Boolean))
        }
      />
      {suggestions.length ? (
        <div className="flex max-h-28 flex-wrap gap-1 overflow-y-auto pt-1">
          {suggestions.slice(0, 12).map((suggestion) => (
            <button
              className={`rounded border px-1.5 py-0.5 text-[11px] ${value.includes(suggestion) ? "border-[#16784a] bg-[#e8f5ee] text-[#145c3a]" : "border-[#d6dee8] bg-white text-[#64748b]"}`}
              key={suggestion}
              type="button"
              onClick={() => onChange(value.includes(suggestion) ? value.filter((item) => item !== suggestion) : [...value, suggestion])}
            >
              {suggestion}
            </button>
          ))}
        </div>
      ) : null}
    </ScopeField>
  );
}

function ScopeField({ label, children }: { label: string; children: ReactNode }) {
  return <div className="space-y-1.5"><Label>{label}</Label>{children}</div>;
}

function selectionLabel(selection: ResultScope["selection"]) {
  return {
    latest_successful_per_sample: "Latest successful",
    specific_methods: "Specific methods",
    specific_versions: "Specific versions",
    specific_runs: "Specific runs",
    pinned_results: "Pinned results",
  }[selection];
}

function readableId(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
