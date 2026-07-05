import { useEffect, useMemo, useRef, useState } from "react";
import { HexColorInput, HexColorPicker } from "react-colorful";
import {
  ChevronDown,
  Copy,
  Database,
  MoreHorizontal,
  Plus,
  Search,
} from "lucide-react";
import type { DataContract, DataContractField, DatabaseTable } from "../../api";
import { CHART_COLORS } from "../../lib/chartColors";
import {
  Button,
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
import { isRecord } from "../reports/reportUtils";

type QueryMode = "contract" | "table";
type SourceTab = "contracts" | "sql";
type Store = DatabaseTable["store"];
type ContractFieldGroup = { contract: DataContract; fields: DataContractField[] };
type ContractFieldOption = {
  id: string;
  contract: DataContract;
  field: DataContractField;
};

export type BuilderSeries = {
  id: string;
  contractId: string;
  fieldId: string;
  aggregation: string;
  name: string;
  color: string;
};

export type SqlSourceSelection = {
  store: Store;
  table: string;
  xField: string;
  yField: string;
};

export function InsightSeriesEditor({
  contracts,
  tables = [],
  sourceKind = "contract",
  store = "analytics",
  table = "",
  xField = "",
  yField = "",
  advancedSql = "",
  series,
  setSeries,
  onAdvancedSqlChange,
  onContractFieldSelect,
  onSqlSourceSelect,
}: {
  contracts: DataContract[];
  tables?: DatabaseTable[];
  sourceKind?: QueryMode;
  store?: Store;
  table?: string;
  xField?: string;
  yField?: string;
  advancedSql?: string;
  series: BuilderSeries[];
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>;
  onAdvancedSqlChange?: (value: string) => void;
  onContractFieldSelect?: (selection: {
    contractId: string;
    fieldId: string;
  }) => void;
  onSqlSourceSelect?: (selection: SqlSourceSelection) => void;
}) {
  return (
    <div className="space-y-3">
      <Label>Series</Label>
      {series.map((item, index) => {
        const contract = contracts.find(
          (candidate) => candidate.data_contract_id === item.contractId,
        );
        const field = contract?.fields.find(
          (candidate) => candidate.field_id === item.fieldId,
        );
        return (
          <SeriesCard
            advancedSql={advancedSql}
            field={field}
            index={index}
            item={item}
            key={item.id}
            contracts={contracts}
            setSeries={setSeries}
            sourceKind={sourceKind}
            store={store}
            table={table}
            tables={tables}
            xField={xField}
            yField={yField}
            onAdvancedSqlChange={onAdvancedSqlChange}
            onContractFieldSelect={onContractFieldSelect}
            onSqlSourceSelect={onSqlSourceSelect}
          />
        );
      })}
      <Button
        className="w-full justify-center"
        size="sm"
        variant="outline"
        onClick={() =>
          setSeries((current) => {
            const previous = current[current.length - 1] ?? current[0];
            return [
              ...current,
              blankSeries(current.length, previous?.contractId ?? "", ""),
            ];
          })
        }
      >
        <Plus className="h-4 w-4" /> Series
      </Button>
    </div>
  );
}

export function blankSeries(
  index: number,
  contractId: string,
  fieldId: string,
): BuilderSeries {
  return {
    id: `series-${Date.now()}-${index}-${Math.random().toString(16).slice(2)}`,
    contractId,
    fieldId,
    aggregation: "avg",
    name: "",
    color: CHART_COLORS[index % CHART_COLORS.length],
  };
}

export function contractSeries(
  contractId: string,
  contracts: DataContract[],
  current: BuilderSeries,
): BuilderSeries {
  const contract = contracts.find(
    (candidate) => candidate.data_contract_id === contractId,
  );
  const field =
    contract?.fields.length === 1
      ? contract.fields[0]
      : contract?.fields.find((candidate) => candidate.value_type === "numeric");
  return {
    ...current,
    contractId,
    fieldId: field?.field_id ?? "",
    name: current.name,
  };
}

export function fieldForSeries(
  contracts: DataContract[],
  series: BuilderSeries,
) {
  return contracts
    .find((contract) => contract.data_contract_id === series.contractId)
    ?.fields.find((field) => field.field_id === series.fieldId);
}

export function seriesDisplayName(
  contracts: DataContract[],
  series: BuilderSeries,
) {
  return (
    series.name ||
    fieldForSeries(contracts, series)?.display_name ||
    series.fieldId ||
    "This field"
  );
}

function customSeriesName(
  series: BuilderSeries,
  field: DataContractField | undefined,
) {
  return series.name && series.name !== field?.display_name ? series.name : "";
}

function SeriesCard({
  advancedSql,
  field,
  index,
  item,
  contracts,
  setSeries,
  sourceKind,
  store,
  table,
  tables,
  xField,
  yField,
  onAdvancedSqlChange,
  onContractFieldSelect,
  onSqlSourceSelect,
}: {
  advancedSql: string;
  field: DataContractField | undefined;
  index: number;
  item: BuilderSeries;
  contracts: DataContract[];
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>;
  sourceKind: QueryMode;
  store: Store;
  table: string;
  tables: DatabaseTable[];
  xField: string;
  yField: string;
  onAdvancedSqlChange?: (value: string) => void;
  onContractFieldSelect?: (selection: {
    contractId: string;
    fieldId: string;
  }) => void;
  onSqlSourceSelect?: (selection: SqlSourceSelection) => void;
}) {
  const [renameOpen, setRenameOpen] = useState(false);
  return (
    <div className="rounded-md border border-[#d6dee8] bg-white p-3 shadow-sm">
      <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2">
        <ColorPickerTrigger
          color={item.color}
          index={index}
          label={seriesDisplayName(contracts, item)}
          onChange={(color) => updateSeries(setSeries, item.id, { color })}
        />
        <DataSourcePicker
          advancedSql={advancedSql}
          field={field}
          item={item}
          contracts={contracts}
          setSeries={setSeries}
          sourceKind={sourceKind}
          store={store}
          table={table}
          tables={tables}
          xField={xField}
          yField={yField}
          onAdvancedSqlChange={onAdvancedSqlChange}
          onContractFieldSelect={onContractFieldSelect}
          onSqlSourceSelect={onSqlSourceSelect}
        />
        <SeriesActions
          field={field}
          index={index}
          item={item}
          setSeries={setSeries}
          onRename={() => setRenameOpen(true)}
          onResetName={() => updateSeries(setSeries, item.id, { name: "" })}
        />
      </div>
      <div className="mt-3 space-y-2">
        <AggregationSelect item={item} setSeries={setSeries} />
        <FieldSummary field={sourceKind === "contract" ? field : undefined} />
      </div>
      <RenameSeriesDialog
        defaultName={field?.display_name || `Series ${index + 1}`}
        open={renameOpen}
        value={customSeriesName(item, field)}
        onOpenChange={setRenameOpen}
        onRename={(name) => updateSeries(setSeries, item.id, { name })}
      />
    </div>
  );
}

function ColorPickerTrigger({
  color,
  index,
  label,
  onChange,
}: {
  color: string;
  index: number;
  label: string;
  onChange: (color: string) => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          aria-label={`Choose color for ${label}`}
          className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-full border border-black/10 text-xs font-semibold text-white shadow-sm outline-none transition-transform hover:scale-105 focus-visible:ring-2 focus-visible:ring-[#21a66a]"
          style={{ backgroundColor: color }}
          type="button"
        >
          {String.fromCharCode(65 + index)}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[244px]">
        <div className="space-y-3 p-2">
          <HexColorPicker color={color} onChange={onChange} />
          <div className="space-y-1.5">
            <Label>Hex</Label>
            <HexColorInput
              className="flex min-h-[38px] w-full rounded-lg border border-[#cfd8e3] bg-white px-3 py-1 font-mono text-sm uppercase outline-none transition-colors focus:ring-2 focus:ring-[#21a66a]"
              color={color}
              prefixed
              onChange={onChange}
            />
          </div>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SeriesActions({
  field,
  index,
  item,
  setSeries,
  onRename,
  onResetName,
}: {
  field: DataContractField | undefined;
  index: number;
  item: BuilderSeries;
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>;
  onRename: () => void;
  onResetName: () => void;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button aria-label="Series actions" size="icon" variant="ghost">
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[180px]">
        <DropdownMenuItem onClick={onRename}>Rename</DropdownMenuItem>
        {customSeriesName(item, field) ? (
          <DropdownMenuItem onClick={onResetName}>Reset name</DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={() =>
            setSeries((current) => duplicateSeries(current, item, field, index))
          }
        >
          <Copy className="h-4 w-4" /> Duplicate series
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          disabled={index === 0}
          onClick={() =>
            setSeries((current) =>
              current.filter((candidate) => candidate.id !== item.id),
            )
          }
        >
          Delete series
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function RenameSeriesDialog({
  defaultName,
  open,
  value,
  onOpenChange,
  onRename,
}: {
  defaultName: string;
  open: boolean;
  value: string;
  onOpenChange: (value: boolean) => void;
  onRename: (value: string) => void;
}) {
  const [draft, setDraft] = useState(value || defaultName);

  useEffect(() => {
    if (open) setDraft(value || defaultName);
  }, [defaultName, open, value]);

  const save = () => {
    const trimmed = draft.trim();
    onRename(trimmed === defaultName ? "" : trimmed);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rename series</DialogTitle>
        </DialogHeader>
        <Input
          autoFocus
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") save();
          }}
        />
        <DialogFooter>
          <DialogClose asChild>
            <Button type="button" variant="outline">
              Cancel
            </Button>
          </DialogClose>
          <Button type="button" onClick={save}>
            Rename
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function duplicateSeries(
  current: BuilderSeries[],
  item: BuilderSeries,
  field: DataContractField | undefined,
  index: number,
) {
  const source = current.find((candidate) => candidate.id === item.id);
  if (!source) return current;
  const sourceIndex = current.findIndex((candidate) => candidate.id === item.id);
  const copyName = source.name || field?.display_name || `Series ${index + 1}`;
  const duplicate = {
    ...source,
    id: `series-${Date.now()}-${current.length}-${Math.random()
      .toString(16)
      .slice(2)}`,
    name: `${copyName} copy`,
    color: CHART_COLORS[current.length % CHART_COLORS.length],
  };
  return [
    ...current.slice(0, sourceIndex + 1),
    duplicate,
    ...current.slice(sourceIndex + 1),
  ];
}

function DataSourcePicker({
  advancedSql,
  field,
  item,
  contracts,
  setSeries,
  sourceKind,
  store,
  table,
  tables,
  xField,
  yField,
  onAdvancedSqlChange,
  onContractFieldSelect,
  onSqlSourceSelect,
}: {
  advancedSql: string;
  field: DataContractField | undefined;
  item: BuilderSeries;
  contracts: DataContract[];
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>;
  sourceKind: QueryMode;
  store: Store;
  table: string;
  tables: DatabaseTable[];
  xField: string;
  yField: string;
  onAdvancedSqlChange?: (value: string) => void;
  onContractFieldSelect?: (selection: {
    contractId: string;
    fieldId: string;
  }) => void;
  onSqlSourceSelect?: (selection: SqlSourceSelection) => void;
}) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<SourceTab>("contracts");
  const [search, setSearch] = useState("");
  const [draftStore, setDraftStore] = useState<Store>(store);
  const [draftTable, setDraftTable] = useState(table);
  const [draftXField, setDraftXField] = useState(xField);
  const [draftYField, setDraftYField] = useState(yField);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const selectedContract = contracts.find(
    (candidate) => candidate.data_contract_id === item.contractId,
  );
  const contractGroups = useMemo(
    () => filterContractGroups(contracts, search),
    [contracts, search],
  );
  const contractOptions = useMemo(
    () => flattenContractOptions(contractGroups),
    [contractGroups],
  );
  const [activeContractOptionIndex, setActiveContractOptionIndex] = useState(0);
  const stores = useMemo(() => {
    const unique = new Set<Store>(["analytics", "catalog"]);
    for (const candidate of tables) unique.add(candidate.store);
    return Array.from(unique);
  }, [tables]);
  const tablesForStore = tables.filter(
    (candidate) => candidate.store === draftStore,
  );
  const filteredTablesForStore = filterSqlTables(tablesForStore, search);
  const selectedTable =
    tablesForStore.find((candidate) => candidate.name === draftTable) ??
    tablesForStore[0];
  const columns = selectedTable?.columns ?? [];
  const filteredColumns = filterSqlColumns(columns, selectedTable?.name, search);
  const sqlSummary =
    table || advancedSql.trim()
      ? `${store}.${table || "SQL query"}`
      : "Choose SQL source";
  const customName = customSeriesName(item, field);
  const contractSourceLabel =
    customName || field?.display_name || "Choose field";

  useEffect(() => {
    if (open) return;
    setDraftStore(store);
    setDraftTable(table);
    setDraftXField(xField);
    setDraftYField(yField);
  }, [open, store, table, xField, yField]);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => {
      searchInputRef.current?.focus();
      searchInputRef.current?.select();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  useEffect(() => {
    setActiveContractOptionIndex(0);
  }, [search, tab]);

  useEffect(() => {
    if (contractOptions.length === 0) {
      setActiveContractOptionIndex(0);
      return;
    }
    setActiveContractOptionIndex((current) =>
      Math.min(current, contractOptions.length - 1),
    );
  }, [contractOptions.length]);

  const selectField = (contract: DataContract, nextField: DataContractField) => {
    setSeries((current) =>
      current.map((candidate) =>
        candidate.id === item.id
          ? {
              ...candidate,
              contractId: contract.data_contract_id,
              fieldId: nextField.field_id,
              name:
                candidate.name && candidate.name !== field?.display_name
                  ? candidate.name
                  : "",
            }
          : candidate,
      ),
    );
    onContractFieldSelect?.({
      contractId: contract.data_contract_id,
      fieldId: nextField.field_id,
    });
    setOpen(false);
  };

  const selectContractOption = (option: ContractFieldOption) => {
    selectField(option.contract, option.field);
  };

  const handleSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (tab !== "contracts" || contractOptions.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveContractOptionIndex((current) =>
        current + 1 >= contractOptions.length ? 0 : current + 1,
      );
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveContractOptionIndex((current) =>
        current - 1 < 0 ? contractOptions.length - 1 : current - 1,
      );
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const option = contractOptions[activeContractOptionIndex];
      if (option) selectContractOption(option);
    }
  };

  const changeDraftStore = (value: Store) => {
    const nextTable = tables.find((candidate) => candidate.store === value);
    setDraftStore(value);
    setDraftTable(nextTable?.name ?? "");
    setDraftXField(nextTable?.columns[0] ?? "");
    setDraftYField(defaultYColumn(nextTable?.columns ?? []));
  };

  const changeDraftTable = (value: string) => {
    const nextTable = tables.find(
      (candidate) =>
        candidate.store === draftStore && candidate.name === value,
    );
    setDraftTable(value);
    setDraftXField(nextTable?.columns[0] ?? "");
    setDraftYField(defaultYColumn(nextTable?.columns ?? []));
  };

  const useSqlSource = () => {
    const nextTable =
      selectedTable ??
      tables.find((candidate) => candidate.store === draftStore) ??
      tables[0];
    const nextColumns = nextTable?.columns ?? [];
    onSqlSourceSelect?.({
      store: nextTable?.store ?? draftStore,
      table: nextTable?.name ?? draftTable,
      xField: draftXField || nextColumns[0] || "",
      yField: draftYField || defaultYColumn(nextColumns),
    });
    setOpen(false);
  };

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          className="h-auto w-full justify-between gap-3 px-3 py-1.5 text-left"
          type="button"
          variant="outline"
        >
          <span className="flex min-w-0 items-center gap-2">
            <Database className="h-4 w-4 shrink-0 text-[#657082]" />
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold text-[#1f2937]">
                {sourceKind === "table"
                  ? sqlSummary
                  : contractSourceLabel}
              </span>
            </span>
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-[#657082]" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[min(560px,92vw)] p-3">
        <div className="space-y-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#758195]" />
            <Input
              className="pl-9 pr-[128px]"
              placeholder={
                tab === "contracts"
                  ? "Search fields..."
                  : "Search tables or columns..."
              }
              ref={searchInputRef}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onKeyDown={handleSearchKeyDown}
            />
            <div className="absolute right-1 top-1/2 w-[118px] -translate-y-1/2">
              <Select
                value={tab}
                onValueChange={(value) => setTab(value as SourceTab)}
              >
                <SelectTrigger className="h-8 border-transparent bg-[#eef2f6] px-2 text-sm shadow-none">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="contracts">Fields</SelectItem>
                  <SelectItem value="sql">SQL</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          {tab === "contracts" ? (
            <ContractSourceList
              activeOptionId={contractOptions[activeContractOptionIndex]?.id}
              groups={contractGroups}
              search={search}
              selectedFieldId={item.fieldId}
              selectedContractId={item.contractId}
              onActiveOptionChange={(optionId) => {
                const index = contractOptions.findIndex(
                  (option) => option.id === optionId,
                );
                if (index >= 0) setActiveContractOptionIndex(index);
              }}
              onSelect={selectField}
            />
          ) : (
            <SqlSourceForm
              advancedSql={advancedSql}
              columns={filteredColumns}
              draftStore={draftStore}
              draftTable={draftTable}
              draftXField={draftXField}
              draftYField={draftYField}
              stores={stores}
              tables={filteredTablesForStore}
              onAdvancedSqlChange={onAdvancedSqlChange}
              onDraftStoreChange={changeDraftStore}
              onDraftTableChange={changeDraftTable}
              onDraftXFieldChange={setDraftXField}
              onDraftYFieldChange={setDraftYField}
              onUseSqlSource={useSqlSource}
            />
          )}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ContractSourceList({
  activeOptionId,
  groups,
  search,
  selectedFieldId,
  selectedContractId,
  onActiveOptionChange,
  onSelect,
}: {
  activeOptionId: string | undefined;
  groups: ContractFieldGroup[];
  search: string;
  selectedFieldId: string;
  selectedContractId: string;
  onActiveOptionChange: (optionId: string) => void;
  onSelect: (contract: DataContract, field: DataContractField) => void;
}) {
  useEffect(() => {
    if (!activeOptionId) return;
    document
      .getElementById(contractOptionDomId(activeOptionId))
      ?.scrollIntoView({ block: "nearest" });
  }, [activeOptionId]);

  return (
    <div className="max-h-[360px] space-y-3 overflow-y-auto pr-1">
      {groups.map(({ contract, fields }) => (
        <section
          className="rounded-md border border-[#d9e1ea] bg-white"
          key={contract.data_contract_id}
        >
          <div className="flex items-center justify-between gap-3 border-b border-[#e8edf3] px-3 py-2">
            <div className="group relative min-w-0">
              <div className="truncate text-xs font-bold uppercase tracking-wide text-[#657082]">
                {highlightSearchMatch(contract.name.toUpperCase(), search)}
              </div>
              <div className="pointer-events-none absolute left-0 top-full z-50 mt-2 w-[300px] rounded-md border border-[#d6dee8] bg-white p-2 text-xs leading-5 text-[#526071] opacity-0 shadow-[0_12px_30px_rgb(0_0_0/0.14)] transition-opacity delay-700 group-hover:opacity-100">
                <div className="font-semibold text-[#1f2937]">
                  {contract.name}
                </div>
                <div>{contract.data_contract_id}</div>
                {contract.data_type ? <div>{contract.data_type}</div> : null}
              </div>
            </div>
            <div className="shrink-0 text-xs text-[#657082]">
              {fields.length} fields
            </div>
          </div>
          <div className="grid gap-1 p-2">
            {fields.map((candidate) => {
              const optionId = contractOptionId(contract, candidate);
              const active = activeOptionId === optionId;
              const selected =
                selectedContractId === contract.data_contract_id &&
                selectedFieldId === candidate.field_id;
              return (
                <button
                  className={[
                    "group relative grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-md px-2 py-2.5 text-left text-sm transition-colors",
                    selected
                      ? "bg-[#e8f5ee] text-[#16784a]"
                      : active
                        ? "bg-[#f4f8fb] text-[#1f2937]"
                        : "hover:bg-white",
                  ].join(" ")}
                  id={contractOptionDomId(optionId)}
                  key={candidate.field_id}
                  type="button"
                  onClick={() => onSelect(contract, candidate)}
                  onMouseEnter={() => onActiveOptionChange(optionId)}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[15px] font-semibold">
                      {highlightSearchMatch(
                        candidate.display_name || candidate.field_id,
                        search,
                      )}
                    </span>
                  </span>
                  <span className="rounded bg-[#eef3f7] px-2 py-1 text-xs text-[#526071]">
                    {candidate.value_type}
                  </span>
                  <span className="pointer-events-none absolute left-2 top-full z-50 mt-1 w-[300px] rounded-md border border-[#d6dee8] bg-white p-2 text-xs leading-5 text-[#526071] opacity-0 shadow-[0_12px_30px_rgb(0_0_0/0.14)] transition-opacity delay-700 group-hover:opacity-100">
                    <span className="block font-semibold text-[#1f2937]">
                      {highlightSearchMatch(
                        candidate.display_name || candidate.field_id,
                        search,
                      )}
                    </span>
                    <span className="block">
                      {highlightSearchMatch(candidate.field_id, search)}
                    </span>
                    {candidate.description ? (
                      <span className="block">
                        {highlightSearchMatch(candidate.description, search)}
                      </span>
                    ) : null}
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      ))}
      {groups.length === 0 ? (
        <div className="rounded-md border border-dashed border-[#d6dee8] p-4 text-sm text-[#657082]">
          No matching contract fields.
        </div>
      ) : null}
    </div>
  );
}

function SqlSourceForm({
  advancedSql,
  columns,
  draftStore,
  draftTable,
  draftXField,
  draftYField,
  stores,
  tables,
  onAdvancedSqlChange,
  onDraftStoreChange,
  onDraftTableChange,
  onDraftXFieldChange,
  onDraftYFieldChange,
  onUseSqlSource,
}: {
  advancedSql: string;
  columns: string[];
  draftStore: Store;
  draftTable: string;
  draftXField: string;
  draftYField: string;
  stores: Store[];
  tables: DatabaseTable[];
  onAdvancedSqlChange?: (value: string) => void;
  onDraftStoreChange: (value: Store) => void;
  onDraftTableChange: (value: string) => void;
  onDraftXFieldChange: (value: string) => void;
  onDraftYFieldChange: (value: string) => void;
  onUseSqlSource: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>Store</Label>
          <Select
            value={draftStore}
            onValueChange={(value) => onDraftStoreChange(value as Store)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {stores.map((value) => (
                <SelectItem key={value} value={value}>
                  {value === "analytics" ? "DuckDB analytics" : "SQL catalog"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>Table</Label>
          <Select value={draftTable} onValueChange={onDraftTableChange}>
            <SelectTrigger>
              <SelectValue placeholder="Choose a table" />
            </SelectTrigger>
            <SelectContent>
              {tables.map((candidate) => (
                <SelectItem
                  key={`${candidate.store}:${candidate.name}`}
                  value={candidate.name}
                >
                  {candidate.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label>X / group</Label>
          <Select value={draftXField} onValueChange={onDraftXFieldChange}>
            <SelectTrigger>
              <SelectValue placeholder="Column" />
            </SelectTrigger>
            <SelectContent>
              {columns.map((column) => (
                <SelectItem key={column} value={column}>
                  {column}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>Y / value</Label>
          <Select value={draftYField} onValueChange={onDraftYFieldChange}>
            <SelectTrigger>
              <SelectValue placeholder="Column" />
            </SelectTrigger>
            <SelectContent>
              {columns.map((column) => (
                <SelectItem key={column} value={column}>
                  {column}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>SQL query</Label>
        <textarea
          className="min-h-[96px] w-full resize-y rounded-lg border border-[#cfd8e3] bg-white p-2 font-mono text-xs outline-none focus:ring-2 focus:ring-[#21a66a]"
          placeholder="SELECT ... (optional)"
          value={advancedSql}
          onChange={(event) => onAdvancedSqlChange?.(event.target.value)}
        />
      </div>
      <Button className="w-full justify-center" onClick={onUseSqlSource}>
        Use SQL source
      </Button>
    </div>
  );
}

function filterContractGroups(contracts: DataContract[], search: string) {
  const normalized = search.trim().toLowerCase();
  return contracts
    .map((contract) => {
      const contractText = [
        contract.name,
        contract.data_contract_id,
        contract.data_type,
        contract.assay,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      const contractMatches = normalized && contractText.includes(normalized);
      const fields = normalized
        ? contract.fields.filter((field) => {
            if (contractMatches) return true;
            return [
              field.display_name,
              field.field_id,
              field.value_type,
              field.description,
            ]
              .filter(Boolean)
              .join(" ")
              .toLowerCase()
              .includes(normalized);
          })
        : contract.fields;
      return fields.length ? { contract, fields } : null;
    })
    .filter(
      (group): group is { contract: DataContract; fields: DataContractField[] } =>
        Boolean(group),
    );
}

function flattenContractOptions(groups: ContractFieldGroup[]): ContractFieldOption[] {
  return groups.flatMap(({ contract, fields }) =>
    fields.map((field) => ({
      id: contractOptionId(contract, field),
      contract,
      field,
    })),
  );
}

function contractOptionId(contract: DataContract, field: DataContractField) {
  return `${contract.data_contract_id}::${field.field_id}`;
}

function contractOptionDomId(optionId: string) {
  return `contract-source-${optionId.replace(/[^a-zA-Z0-9_-]/g, "_")}`;
}

function highlightSearchMatch(text: string, search: string) {
  const query = search.trim();
  if (!query) return text;
  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  let matchIndex = lowerText.indexOf(lowerQuery, cursor);
  while (matchIndex >= 0) {
    if (matchIndex > cursor) {
      parts.push(text.slice(cursor, matchIndex));
    }
    const end = matchIndex + query.length;
    parts.push(
      <mark
        className="rounded-sm bg-[#dff4e8] px-0.5 text-inherit"
        key={`${matchIndex}-${end}`}
      >
        {text.slice(matchIndex, end)}
      </mark>,
    );
    cursor = end;
    matchIndex = lowerText.indexOf(lowerQuery, cursor);
  }
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts.length ? parts : text;
}

function filterSqlTables(tables: DatabaseTable[], search: string) {
  const normalized = search.trim().toLowerCase();
  if (!normalized) return tables;
  return tables.filter((table) =>
    [table.name, ...table.columns]
      .join(" ")
      .toLowerCase()
      .includes(normalized),
  );
}

function filterSqlColumns(
  columns: string[],
  tableName: string | undefined,
  search: string,
) {
  const normalized = search.trim().toLowerCase();
  if (!normalized || tableName?.toLowerCase().includes(normalized)) {
    return columns;
  }
  return columns.filter((column) => column.toLowerCase().includes(normalized));
}

function defaultYColumn(columns: string[]) {
  return (
    columns.find((column) => column === "value_numeric") ??
    columns.find((column) => column !== "sample_id" && column !== "run_id") ??
    columns[1] ??
    columns[0] ??
    ""
  );
}

function AggregationSelect({
  item,
  setSeries,
}: {
  item: BuilderSeries;
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>;
}) {
  return (
    <Select
      value={item.aggregation}
      onValueChange={(aggregation) =>
        updateSeries(setSeries, item.id, { aggregation })
      }
    >
      <SelectTrigger>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {["count", "sum", "avg", "min", "max"].map((aggregation) => (
          <SelectItem key={aggregation} value={aggregation}>
            {aggregation}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function updateSeries(
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>,
  id: string,
  patch: Partial<BuilderSeries>,
) {
  setSeries((current) =>
    current.map((candidate) =>
      candidate.id === id ? { ...candidate, ...patch } : candidate,
    ),
  );
}

function FieldSummary({ field }: { field: DataContractField | undefined }) {
  if (!field) return null;
  const parts = [
    field.value_type,
    field.unit,
    summaryRange(field.summary),
    topValues(field.summary),
  ].filter(Boolean);
  return (
    <div className="mt-2 space-y-1 text-xs text-[#657082]">
      <div>{parts.join(" · ")}</div>
      {field.description ? <div>{field.description}</div> : null}
    </div>
  );
}

function summaryRange(summary: Record<string, unknown>) {
  const min = summary.min;
  const max = summary.max;
  if (typeof min === "number" && typeof max === "number") {
    return `${min.toLocaleString()} to ${max.toLocaleString()}`;
  }
  return null;
}

function topValues(summary: Record<string, unknown>) {
  const values = summary.top_values;
  if (!Array.isArray(values) || values.length === 0) return null;
  return values
    .slice(0, 3)
    .map((item) =>
      isRecord(item) && "value" in item ? String(item.value) : String(item),
    )
    .join(", ");
}
