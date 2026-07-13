import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import {
  AreaChart,
  BarChart2,
  BarChart3,
  Box,
  Braces,
  ChartScatter,
  Check,
  ChevronDown,
  CircleDot,
  CirclePlay,
  Database,
  Dna,
  File,
  Grid2X2,
  Hash,
  LineChart,
  MoreHorizontal,
  Pencil,
  PieChart,
  Plus,
  Search,
  Table2,
  Trash2,
  User,
  Users,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentType,
  type ReactNode,
  type UIEvent,
} from "react";
import {
  createInsight,
  executeInsight,
  getInsightCatalog,
  listInsights,
  listProjectDatabaseTables,
  listProjectDataContracts,
  listProjectSampleGroups,
  listProjectSamples,
  listReports,
  patchInsight,
  validateInsightConfig,
  type DataContract,
  type DataContractField,
  type DatabaseTable,
  type InsightCatalog,
  type InsightValidation,
  type SampleSet,
  type SampleListItem,
  type SavedInsight,
} from "../api";
import { InsightBuilderHeader } from "../components/insights/InsightBuilderHeader";
import { useAuth } from "../components/auth/AuthProvider";
import { InsightChartControls } from "../components/insights/InsightChartControls";
import { InsightPreviewPanel } from "../components/insights/InsightPreviewPanel";
import {
  defaultResultScope,
  type ResultScope,
} from "../components/insights/ResultScopeEditor";
import {
  InsightSeriesEditor,
  blankSeries,
  fieldForSeries,
  contractSeries,
  filterContractGroups,
  seriesDisplayName,
  type BuilderSeries,
  type SqlSourceSelection,
} from "../components/insights/InsightSeriesEditor";
import { InsightListTable } from "../components/reports/InsightListTable";
import { isRecord, readReportItems } from "../components/reports/reportUtils";
import {
  AsyncBlock,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
  Label,
  Page,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../components/ui";
import {
  DEFAULT_DISPLAY_OPTIONS,
  displayOptionsConfig,
  readDisplayOptions,
  type DisplayOptions,
} from "../lib/insightDisplayOptions";
import { CHART_COLORS } from "../lib/chartColors";
import { queryClient } from "../lib/queryClient";

type Store = DatabaseTable["store"];
type InsightMode = "list" | "detail";
type InsightTarget =
  | { mode: "list" }
  | { mode: "new" }
  | { mode: "edit"; insightRef: string };
type QueryMode = "contract" | "table";
type AnalysisGrain =
  | "sample"
  | "subject"
  | "run"
  | "feature"
  | "variant"
  | "file";
type LinkerKind = "auto" | "sample" | "run" | "feature" | "entity";
type ResultPolicyMode =
  | "preview"
  | "more_rows"
  | "random_sample"
  | "all_rows"
  | "export_full_data";
type FilterTab = "sample" | "sample_group";

/** Insight index and builder page for saved charts, metrics, and tables. */
export function InsightsPage({
  projectId,
  target = { mode: "list" },
}: {
  projectId: string;
  target?: InsightTarget;
}) {
  const { can } = useAuth();
  const canCreate = can("insight.create", projectId);
  // These queries feed both the list view and the builder. Contracts provide the
  // semantic route; database tables provide the lower-level escape hatch.
  const insights = useQuery({
    queryKey: ["insights", projectId],
    queryFn: () => listInsights(projectId),
  });
  const tables = useQuery({
    queryKey: ["database-tables", projectId],
    queryFn: () => listProjectDatabaseTables(projectId),
  });
  const contracts = useQuery({
    queryKey: ["data-contracts", projectId],
    queryFn: () => listProjectDataContracts(projectId),
  });
  const reports = useQuery({
    queryKey: ["reports", projectId],
    queryFn: () => listReports(projectId),
  });
  const catalog = useQuery({
    queryKey: ["insight-catalog"],
    queryFn: getInsightCatalog,
  });
  const [mode, setMode] = useState<InsightMode>(
    target.mode === "list" ? "list" : "detail",
  );
  const [search, setSearch] = useState("");
  const [selectedInsightId, setSelectedInsightId] = useState<string | null>(
    null,
  );
  const canSave =
    selectedInsightId || target.mode === "edit"
      ? can("insight.edit", projectId)
      : canCreate;
  const selectedInsight = insights.data?.find(
    (insight) =>
      (target.mode === "edit" &&
        (insight.insight_id === target.insightRef ||
          insight.url_slug === target.insightRef)) ||
      insight.insight_id === selectedInsightId,
  );
  const effectiveSelectedInsightId =
    selectedInsight?.insight_id ?? selectedInsightId;
  const [title, setTitle] = useState("New insight");
  const [description, setDescription] = useState("");
  const [descriptionOpen, setDescriptionOpen] = useState(false);
  const [tableColumnPickerOpen, setTableColumnPickerOpen] = useState(false);
  const [analysisGrain, setAnalysisGrain] = useState<AnalysisGrain>("sample");
  const [sampleSetIds, setSampleSetIds] = useState<string[]>([]);
  const [sampleIds, setSampleIds] = useState<string[]>([]);
  const [runSampleIds, setRunSampleIds] = useState<string[]>([]);
  const [queryMode, setQueryMode] = useState<QueryMode>("contract");
  const [contractId, setContractId] = useState("");
  const [fieldId, setFieldId] = useState("");
  const [series, setSeries] = useState<BuilderSeries[]>([
    blankSeries(0, "", ""),
  ]);
  const [tableColumns, setTableColumns] = useState<BuilderSeries[]>([
    blankSeries(0, "", ""),
  ]);
  const [store, setStore] = useState<Store>("analytics");
  const [table, setTable] = useState("");
  const [visualization, setVisualization] = useState("table");
  const [linkerKind, setLinkerKind] = useState<LinkerKind>("sample");
  const [resultPolicyMode, setResultPolicyMode] =
    useState<ResultPolicyMode>("preview");
  const [resultLimit, setResultLimit] = useState(5000);
  const [randomSeed, setRandomSeed] = useState("goodomics");
  const [displayOptions, setDisplayOptions] = useState<DisplayOptions>(
    DEFAULT_DISPLAY_OPTIONS,
  );
  const [xField, setXField] = useState("");
  const [yField, setYField] = useState("");
  const [advancedSql, setAdvancedSql] = useState("");
  const availableTables = tables.data ?? [];
  const availableContracts = contracts.data ?? [];
  const selectedContract = availableContracts.find(
    (candidate) => candidate.data_contract_id === contractId,
  );
  const selectedTable = availableTables.find(
    (candidate) => candidate.store === store && candidate.name === table,
  );
  const reportCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const report of reports.data ?? []) {
      const insightIds = new Set(
        readReportItems(report.config).map((item) => item.insight_id),
      );
      for (const insightId of insightIds) {
        counts.set(insightId, (counts.get(insightId) ?? 0) + 1);
      }
    }
    return counts;
  }, [reports.data]);
  const selectAnalysisGrain = (next: AnalysisGrain) => {
    setAnalysisGrain(next);
    setLinkerKind(defaultLinkerForGrain(next));
  };
  const applyTemplate = (templateId: string) => {
    const template = templateDefinition(templateId, catalog.data);
    const nextGrain = parseAnalysisGrain(template?.analysis_grain);
    const nextVisualization = stringConfig(template?.visualization) || "table";
    const linker = isRecord(template?.linker) ? template.linker : {};
    const nextContract =
      selectedContract ??
      availableContracts.find((candidate) => candidate.fields.length > 0);
    const firstField = defaultFieldForContract(nextContract, {
      numericOnly: nextVisualization !== "table",
    });
    const secondField = nextContract
      ? (nextContract.fields.find(
          (field) =>
            field.field_id !== firstField &&
            (nextVisualization !== "scatter" || field.value_type === "numeric"),
        )?.field_id ?? "")
      : "";
    const nextContractId = nextContract?.data_contract_id ?? contractId;
    setAnalysisGrain(nextGrain);
    setVisualization(nextVisualization);
    setLinkerKind(
      parseLinkerKind(linker.kind) || defaultLinkerForGrain(nextGrain),
    );
    setQueryMode("contract");
    setSampleSetIds([]);
    setSampleIds([]);
    setRunSampleIds([]);
    if (stringConfig(template?.label)) {
      setTitle(stringConfig(template?.label));
    }
    if (stringConfig(template?.description)) {
      setDescription(stringConfig(template?.description));
    }
    if (nextContractId) {
      setContractId(nextContractId);
    }
    if (firstField) {
      setFieldId(firstField);
    }
    const firstSeries = blankSeries(0, nextContractId, firstField);
    const secondSeries = blankSeries(1, nextContractId, secondField);
    if (nextVisualization === "table") {
      setTableColumns(
        firstField ? [firstSeries] : [blankSeries(0, nextContractId, "")],
      );
      setSeries([firstSeries]);
      return;
    }
    if (nextVisualization === "scatter") {
      setSeries([firstSeries, secondSeries]);
      setTableColumns([firstSeries]);
      return;
    }
    setSeries([firstSeries]);
    setTableColumns([firstSeries]);
  };
  const addAllContractColumns = (contract: DataContract) => {
    setQueryMode("contract");
    setContractId(contract.data_contract_id);
    setTableColumns(
      contract.fields.map((field, index) => ({
        ...blankSeries(index, contract.data_contract_id, field.field_id),
        color: CHART_COLORS[index % CHART_COLORS.length],
      })),
    );
  };
  const addTableColumn = (contract: DataContract, field: DataContractField) => {
    setQueryMode("contract");
    setContractId(contract.data_contract_id);
    setTableColumns((current) => [
      ...current.filter((item) => item.contractId && item.fieldId),
      {
        ...blankSeries(
          current.length,
          contract.data_contract_id,
          field.field_id,
        ),
        name: "",
      },
    ]);
  };
  const resetBuilderValues = () => {
    if (visualization === "table") {
      setTableColumns([blankSeries(0, contractId, "")]);
      return;
    }
    setSeries([blankSeries(0, contractId, "")]);
  };
  const selectContractField = ({
    fieldId: nextFieldId,
    contractId: nextContractId,
  }: {
    contractId: string;
    fieldId: string;
  }) => {
    setQueryMode("contract");
    setContractId(nextContractId);
    setFieldId(nextFieldId);
  };
  const selectSqlSource = (selection: SqlSourceSelection) => {
    setQueryMode("table");
    setVisualization("table");
    setStore(selection.store);
    setTable(selection.table);
    setXField(selection.xField);
    setYField(selection.yField);
  };

  useEffect(() => {
    if (target.mode === "list") {
      setMode("list");
      return;
    }
    setMode("detail");
    if (target.mode === "new") {
      setSelectedInsightId(null);
      setTitle("New insight");
      setDescription("");
      setDescriptionOpen(false);
      setAnalysisGrain("sample");
      setSampleSetIds([]);
      setSampleIds([]);
      setRunSampleIds([]);
      setVisualization("table");
      setLinkerKind("sample");
      setResultPolicyMode("preview");
      setResultLimit(5000);
      setRandomSeed("goodomics");
      setDisplayOptions(DEFAULT_DISPLAY_OPTIONS);
      setAdvancedSql("");
      setQueryMode("contract");
      setSeries([blankSeries(0, "", "")]);
      setTableColumns([blankSeries(0, "", "")]);
      return;
    }
    if (selectedInsight) setSelectedInsightId(selectedInsight.insight_id);
  }, [selectedInsight, target.mode]);

  useEffect(() => {
    // Seed a contract-first insight with the first useful data contract. The
    // contract picker remains the source of truth after the user makes a choice.
    if (contractId || availableContracts.length === 0) return;
    const preferred =
      availableContracts.find((candidate) => candidate.fields.length > 0) ??
      availableContracts[0];
    setContractId(preferred.data_contract_id);
    const defaultField =
      preferred.fields.find((field) => field.value_type === "numeric")
        ?.field_id ??
      preferred.fields[0]?.field_id ??
      "";
    setFieldId(defaultField);
    setSeries((current) =>
      current.map((item, index) =>
        index === 0 && !item.contractId
          ? {
              ...item,
              contractId: preferred.data_contract_id,
              fieldId: defaultField,
            }
          : item,
      ),
    );
    setTableColumns((current) =>
      current.map((item, index) =>
        index === 0 && !item.contractId
          ? {
              ...item,
              contractId: preferred.data_contract_id,
              fieldId: defaultField,
            }
          : item,
      ),
    );
  }, [availableContracts, contractId]);

  useEffect(() => {
    // When the selected contract changes, choose a numeric field by default so
    // chart previews start from a likely-valid metric.
    if (!selectedContract || fieldId) return;
    const defaultField =
      selectedContract.fields.find((field) => field.value_type === "numeric")
        ?.field_id ??
      selectedContract.fields[0]?.field_id ??
      "";
    setFieldId(defaultField);
  }, [fieldId, selectedContract]);

  useEffect(() => {
    // Advanced table mode needs a physical table and default x/y columns. Prefer
    // sample_metrics because it is the most common analytics preview source.
    if (table || availableTables.length === 0) return;
    const preferred =
      availableTables.find(
        (candidate) => candidate.name === "sample_metrics",
      ) ??
      availableTables.find((candidate) => candidate.store === "analytics") ??
      availableTables[0];
    setStore(preferred.store);
    setTable(preferred.name);
    setXField(preferred.columns[0] ?? "");
    setYField(
      preferred.columns.find((column) => column === "value_numeric") ??
        preferred.columns[1] ??
        "",
    );
  }, [availableTables, table]);

  useEffect(() => {
    // Scatter plots require two aligned series. Add the second empty card
    // automatically so the user sees the missing Y-series slot immediately.
    if (queryMode !== "contract" || visualization !== "scatter") {
      return;
    }
    setSeries((current) =>
      current.length >= 2
        ? current
        : [
            ...current,
            blankSeries(
              current.length,
              current[0]?.contractId ?? contractId,
              "",
            ),
          ],
    );
  }, [contractId, queryMode, visualization]);

  useEffect(() => {
    // Contracts can arrive after the series state is initialized. Fill any
    // contract-only series with its default field once metadata is available.
    if (queryMode !== "contract" || availableContracts.length === 0) return;
    setSeries((current) =>
      current.map((item) =>
        item.contractId && !item.fieldId
          ? contractSeries(item.contractId, availableContracts, item)
          : item,
      ),
    );
    setTableColumns((current) =>
      current.map((item) =>
        item.contractId && !item.fieldId
          ? contractSeries(item.contractId, availableContracts, item)
          : item,
      ),
    );
  }, [availableContracts, queryMode]);

  useEffect(() => {
    // Opening a saved insight is the inverse of buildConfig(): parse the saved
    // query source back into editable builder state.
    if (!selectedInsight) return;
    const config = selectedInsight.config;
    const query = isRecord(config.query) ? config.query : {};
    const source = parseSource(query.source);
    const context = isRecord(config.context) ? config.context : {};
    const linker = isRecord(config.linker) ? config.linker : {};
    const resultPolicy = isRecord(config.result_policy)
      ? config.result_policy
      : {};
    setTitle(selectedInsight.name);
    setDescription(selectedInsight.description ?? "");
    setDescriptionOpen(Boolean(selectedInsight.description?.trim()));
    setVisualization(String(config.visualization ?? "table"));
    setAnalysisGrain(parseAnalysisGrain(config.analysis_grain));
    setSampleSetIds(
      stringArrayConfig(context.sample_set_ids, context.sample_set_id),
    );
    setSampleIds(stringArrayConfig(context.sample_ids, context.sample_id));
    setRunSampleIds([]);
    setLinkerKind(parseLinkerKind(linker.kind));
    setResultPolicyMode(parseResultPolicyMode(resultPolicy.mode));
    setResultLimit(numberConfig(resultPolicy.limit, 5000));
    setRandomSeed(stringConfig(resultPolicy.seed) || "goodomics");
    setDisplayOptions(readDisplayOptions(config));
    setQueryMode(source.kind);
    if (source.kind === "contract") {
      setContractId(source.dataContractId);
      const selectedField = firstString(query.y, query.fields, "");
      const savedSeries = parseSavedSeries(
        config.series,
        source.dataContractId,
      );
      setFieldId(selectedField || savedSeries[0]?.fieldId || "");
      setSeries(
        savedSeries.length
          ? savedSeries
          : [
              {
                ...blankSeries(0, source.dataContractId, selectedField),
                aggregation: "raw",
              },
            ],
      );
      const savedColumns = parseSavedSeries(
        config.table_columns,
        source.dataContractId,
      );
      setTableColumns(
        savedColumns.length
          ? savedColumns
          : [
              {
                ...blankSeries(0, source.dataContractId, selectedField),
                aggregation: "raw",
              },
            ],
      );
    } else {
      setStore(source.store);
      setTable(source.table);
    }
    setXField(
      firstString(query.x, query.dimensions, selectedTable?.columns[0]),
    );
    setYField(firstString(query.y, undefined, selectedTable?.columns[1]));
    setAdvancedSql(typeof query.sql === "string" ? query.sql : "");
  }, [selectedInsight, selectedTable?.columns]);

  const config = useMemo(
    // `config` is the persisted insight document. It includes editor metadata
    // such as title/description in addition to the executable query payload.
    () =>
      buildConfig({
        title,
        description,
        analysisGrain,
        sampleSetIds,
        sampleIds,
        runSampleIds,
        queryMode,
        seriesItems: series,
        tableColumnItems: tableColumns,
        contracts: availableContracts,
        selectedContract,
        store,
        table,
        visualization,
        linkerKind,
        resultPolicyMode,
        resultLimit,
        randomSeed,
        displayOptions,
        xField,
        yField,
        advancedSql,
      }),
    [
      advancedSql,
      analysisGrain,
      availableContracts,
      description,
      displayOptions,
      fieldId,
      linkerKind,
      contractId,
      queryMode,
      randomSeed,
      resultLimit,
      resultPolicyMode,
      series,
      tableColumns,
      selectedContract,
      sampleIds,
      sampleSetIds,
      store,
      table,
      title,
      visualization,
      runSampleIds,
      xField,
      yField,
    ],
  );
  const previewConfig = useMemo(() => executionConfig(config), [config]);
  const validation = useQuery({
    queryKey: ["insight-validation", previewConfig],
    queryFn: () => validateInsightConfig(previewConfig),
    enabled: mode === "detail",
    retry: false,
  });
  const preview = useQuery({
    // Preview executes the config as the user edits. React Query keys include
    // the generated config object so chart changes naturally refetch.
    queryKey: [
      "insight-preview",
      projectId,
      effectiveSelectedInsightId,
      previewConfig,
    ],
    queryFn: () =>
      executeInsight({
        insightId: effectiveSelectedInsightId ?? undefined,
        projectId,
        config: previewConfig,
      }),
    enabled:
      mode === "detail" &&
      (queryMode === "contract"
        ? (visualization === "table" ? tableColumns : series).some(
            (item) => item.contractId && item.fieldId,
          )
        : Boolean(table || advancedSql.trim())),
    retry: false,
  });
  const setupWarning =
    chartSetupWarning({
      contracts: availableContracts,
      queryMode,
      series: visualization === "table" ? tableColumns : series,
      visualization,
    }) ?? validationWarning(validation.data);
  const save = useMutation({
    // Saved insights keep the same config shape that report templates consume,
    // so the dashboard builder and portable YAML/JSON exports stay aligned.
    mutationFn: (continueEditing: boolean) =>
      effectiveSelectedInsightId
        ? patchInsight(effectiveSelectedInsightId, {
            name: title,
            description,
            config,
          })
        : createInsight({
            project_id: projectId,
            name: title,
            description,
            config,
          }),
    onSuccess: (saved, continueEditing) => {
      setSelectedInsightId(saved.insight_id);
      void queryClient.invalidateQueries({ queryKey: ["insights", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["reports", projectId] });
      void queryClient.invalidateQueries({
        queryKey: ["insight-preview", projectId, saved.insight_id],
      });
      window.location.href = continueEditing
        ? `/project/${projectId}/insights/${encodeURIComponent(saved.url_slug)}/edit`
        : `/project/${projectId}/insights`;
    },
  });

  if (mode === "list") {
    return (
      <Page
        title="Insights"
        subtitle="Create reusable charts, metrics, and tables."
      >
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="relative w-full max-w-[320px]">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#758195]" />
            <Input
              className="pl-9"
              placeholder="Search insights..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          {canCreate && (
            <Button
              onClick={() => {
                window.location.href = `/project/${projectId}/insights/new`;
              }}
            >
              <Plus className="h-4 w-4" /> New insight
            </Button>
          )}
        </div>
        <AsyncBlock query={insights} empty="No saved insights yet.">
          {(data) => (
            <InsightListTable
              insights={filterInsights(data, search)}
              reportCounts={reportCounts}
              onOpen={(insight) => {
                window.location.href = `/project/${projectId}/insights/${encodeURIComponent(
                  insight.url_slug,
                )}/edit`;
              }}
            />
          )}
        </AsyncBlock>
      </Page>
    );
  }

  return (
    <div className="flex h-[calc(100vh-48px)] min-h-0 flex-col gap-1 overflow-hidden">
      <InsightBuilderHeader
        description={description}
        descriptionOpen={descriptionOpen}
        isSaving={save.isPending}
        canSave={canSave}
        title={title}
        onBack={() => {
          window.location.href = `/project/${projectId}/insights`;
        }}
        onDescriptionChange={setDescription}
        onDescriptionOpenChange={setDescriptionOpen}
        onSave={() => save.mutate(false)}
        onSaveContinue={() => save.mutate(true)}
        onTitleChange={setTitle}
      />
      <InsightBuilderControls
        analysisGrain={analysisGrain}
        catalog={catalog.data}
        description={description}
        settings={
          <InsightChartControls
            config={previewConfig}
            displayOptions={displayOptions}
            randomSeed={randomSeed}
            result={preview.data}
            resultPolicyMode={resultPolicyMode}
            rowLimit={resultLimit}
            onRandomSeedChange={setRandomSeed}
            onDisplayOptionsChange={setDisplayOptions}
            onResultPolicyModeChange={setResultPolicyMode}
            onRowLimitChange={setResultLimit}
          />
        }
        resetLabel={
          visualization === "table" ? "Clear columns" : "Clear series"
        }
        visualization={visualization}
        onAnalysisGrainChange={selectAnalysisGrain}
        onDescriptionRequest={() => setDescriptionOpen(true)}
        onResetBuilder={resetBuilderValues}
        onTemplateSelect={applyTemplate}
        onVisualizationChange={setVisualization}
      />

      <div
        className={[
          "grid min-h-0 flex-1 grid-cols-1 gap-2 overflow-hidden",
          visualization === "table" ? "" : "lg:grid-cols-[310px_minmax(0,1fr)]",
        ].join(" ")}
      >
        {visualization === "table" ? null : (
          <div className="min-h-0 space-y-2 overflow-y-auto">
            <Card className="mt-0 p-2.5">
              <CardContent className="space-y-2">
                <InsightSeriesEditor
                  addLabel="Add series"
                  advancedSql={advancedSql}
                  contracts={availableContracts}
                  projectId={projectId}
                  itemLabel="Series"
                  label={
                    visualization === "scatter" ? "X / Y data" : "Data series"
                  }
                  series={series}
                  setSeries={setSeries}
                  sourceKind={queryMode}
                  store={store}
                  table={table}
                  tables={availableTables}
                  xField={xField}
                  yField={yField}
                  onAdvancedSqlChange={setAdvancedSql}
                  onContractFieldSelect={selectContractField}
                  onSqlSourceSelect={selectSqlSource}
                />
                {needsLinkerStrip(visualization, series) ? (
                  <LinkerStrip
                    catalog={catalog.data}
                    linkerKind={linkerKind}
                    series={series}
                    onLinkerKindChange={setLinkerKind}
                  />
                ) : null}
              </CardContent>
            </Card>
            <Card className="mt-0 p-2.5">
              <CardContent>
                <SampleFilterDropdown
                  projectId={projectId}
                  runSampleIds={runSampleIds}
                  sampleGroupIds={sampleSetIds}
                  sampleIds={sampleIds}
                  onRunSampleIdsChange={setRunSampleIds}
                  onSampleGroupIdsChange={setSampleSetIds}
                  onSampleIdsChange={setSampleIds}
                />
              </CardContent>
            </Card>
          </div>
        )}

        <InsightPreviewPanel
          config={previewConfig}
          error={preview.error instanceof Error ? preview.error : null}
          result={preview.data}
          setupWarning={setupWarning}
          tableActions={
            visualization === "table"
              ? {
                  addLabel: "Add table column",
                  emptyLabel: "Select data",
                  onAddColumn: () => setTableColumnPickerOpen(true),
                }
              : undefined
          }
        />
      </div>
      <TableColumnPickerDialog
        contracts={availableContracts}
        open={tableColumnPickerOpen}
        selectedColumns={tableColumns}
        onAddAll={addAllContractColumns}
        onOpenChange={setTableColumnPickerOpen}
        onSelect={(contract, field) => {
          addTableColumn(contract, field);
          setTableColumnPickerOpen(false);
        }}
      />
    </div>
  );
}

function safeFieldAlias(value: string) {
  // The server can return safe aliases for contract fields with punctuation. Use
  // the same aliasing rule when building x/y fields and color map keys.
  return value
    .replace(/[^a-zA-Z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}

function chartSetupWarning({
  contracts,
  queryMode,
  series,
  visualization,
}: {
  contracts: DataContract[];
  queryMode: QueryMode;
  series: BuilderSeries[];
  visualization: string;
}) {
  // Warnings are advisory overlays; the server still validates the executable
  // config and returns concrete errors for invalid queries.
  if (queryMode !== "contract") return null;
  const activeSeries = series.filter((item) => item.contractId && item.fieldId);
  if (activeSeries.length === 0) {
    return "Select a data series to preview this insight.";
  }
  if (visualization === "scatter" && activeSeries.length < 2) {
    return "Scatter plots need two aligned numeric series.";
  }
  if (["histogram", "scatter"].includes(visualization)) {
    const nonNumeric = activeSeries
      .slice(0, visualization === "scatter" ? 2 : activeSeries.length)
      .find(
        (item) => fieldForSeries(contracts, item)?.value_type !== "numeric",
      );
    if (nonNumeric) {
      return `${seriesDisplayName(contracts, nonNumeric)} must be numeric for this chart type.`;
    }
  }
  return null;
}

function seriesColorMap(contracts: DataContract[], series: BuilderSeries[]) {
  // Store colors under every label the renderer might see: raw field IDs, safe
  // field aliases, display labels, and the generated Count series.
  const entries = series.flatMap((item, index) => {
    const label = seriesLabel(contracts, item, index);
    const values = [
      [item.fieldId, item.color],
      [safeFieldAlias(item.fieldId), item.color],
      [safeFieldAlias(label), item.color],
    ];
    if (index === 0) {
      values.push(["Count", item.color], ["count", item.color]);
    }
    return values;
  });
  return Object.fromEntries(entries);
}

function seriesLabel(
  contracts: DataContract[],
  item: BuilderSeries,
  index: number,
) {
  return (
    item.name ||
    fieldForSeries(contracts, item)?.display_name ||
    item.fieldId ||
    `Series ${index + 1}`
  );
}

function defaultFieldForContract(
  contract: DataContract | undefined,
  { numericOnly = false }: { numericOnly?: boolean } = {},
) {
  if (!contract) return "";
  const numericField = contract.fields.find(
    (field) => field.value_type === "numeric",
  )?.field_id;
  if (numericOnly) return numericField ?? "";
  return numericField ?? contract.fields[0]?.field_id ?? "";
}

function normalizedSeriesFilters(item: BuilderSeries) {
  return item.filters
    .filter((filter) => filter.field.trim() && filter.value.trim())
    .map((filter) => ({
      field: filter.field.trim(),
      operator: filter.operator || "eq",
      value: coerceFilterValue(filter.value),
    }));
}

function coerceFilterValue(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  const numeric = Number(trimmed);
  return Number.isFinite(numeric) && trimmed !== "" ? numeric : trimmed;
}

function SampleFilterDropdown({
  projectId,
  runSampleIds,
  sampleGroupIds,
  sampleIds,
  onRunSampleIdsChange,
  onSampleGroupIdsChange,
  onSampleIdsChange,
}: {
  projectId: string;
  runSampleIds: string[];
  sampleGroupIds: string[];
  sampleIds: string[];
  onRunSampleIdsChange: (value: string[]) => void;
  onSampleGroupIdsChange: (value: string[]) => void;
  onSampleIdsChange: (value: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<FilterTab>(
    filterTabForSelection({ runSampleIds, sampleGroupIds, sampleIds }),
  );
  const [pendingSampleGroupIds, setPendingSampleGroupIds] =
    useState<string[]>(sampleGroupIds);
  const [pendingSampleIds, setPendingSampleIds] = useState<string[]>(sampleIds);
  const [pendingRunSampleIds, setPendingRunSampleIds] =
    useState<string[]>(runSampleIds);
  const [sampleSearch, setSampleSearch] = useState("");
  const [sampleGroupSearch, setSampleGroupSearch] = useState("");
  const pageSize = 20;
  const samplePages = useInfiniteQuery({
    queryKey: ["insight-filter-samples", projectId, sampleSearch],
    queryFn: ({ pageParam }) =>
      listProjectSamples({
        projectId,
        limit: pageSize,
        offset: pageParam,
        search: sampleSearch,
      }),
    enabled: open && activeTab === "sample",
    initialPageParam: 0,
    getNextPageParam: pageNextOffset,
  });
  const sampleGroupPages = useInfiniteQuery({
    queryKey: ["insight-filter-sample-groups", projectId, sampleGroupSearch],
    queryFn: ({ pageParam }) =>
      listProjectSampleGroups({
        projectId,
        limit: pageSize,
        offset: pageParam,
        search: sampleGroupSearch,
      }),
    enabled: open && activeTab === "sample_group",
    initialPageParam: 0,
    getNextPageParam: pageNextOffset,
  });
  const samples = useMemo(
    () => (samplePages.data?.pages ?? []).flatMap((page) => page.items),
    [samplePages.data?.pages],
  );
  const sampleGroups = useMemo(
    () => (sampleGroupPages.data?.pages ?? []).flatMap((page) => page.items),
    [sampleGroupPages.data?.pages],
  );
  const selectedGroup = sampleGroups.find((sampleGroup) =>
    sampleGroupIds.includes(sampleGroup.sample_set_id),
  );
  const summary = sampleFilterSummary({
    runSampleIds,
    sampleGroup: selectedGroup,
    sampleGroupIds,
    sampleIds,
  });

  useEffect(() => {
    if (!open) {
      setActiveTab(
        filterTabForSelection({ runSampleIds, sampleGroupIds, sampleIds }),
      );
      return;
    }
    setPendingSampleGroupIds(sampleGroupIds);
    setPendingSampleIds(sampleIds);
    setPendingRunSampleIds(runSampleIds);
  }, [open, runSampleIds, sampleGroupIds, sampleIds]);

  const clearFilters = () => {
    setPendingSampleGroupIds([]);
    setPendingSampleIds([]);
    setPendingRunSampleIds([]);
  };
  const commitFilters = () => {
    onSampleGroupIdsChange(pendingSampleGroupIds);
    onSampleIdsChange(pendingSampleIds);
    onRunSampleIdsChange(pendingRunSampleIds);
    setOpen(false);
  };
  const selectSample = (value: string) => {
    setPendingSampleIds((current) => toggleString(current, value));
    setPendingSampleGroupIds([]);
    setPendingRunSampleIds([]);
  };
  const selectSampleGroup = (value: string) => {
    setPendingSampleGroupIds((current) => toggleString(current, value));
    setPendingSampleIds([]);
    setPendingRunSampleIds([]);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          aria-label="Filter by sample or group"
          className="h-10 w-full justify-between bg-white px-3 font-normal text-[#1f2937]"
          type="button"
          variant="outline"
        >
          <span className="truncate">{summary}</span>
          <ChevronDown className="h-4 w-4 shrink-0 text-[#758195]" />
        </Button>
      </DialogTrigger>
      <DialogContent
        className="flex h-[min(760px,92vh)] max-h-[92vh] max-w-[min(720px,94vw)] flex-col gap-3 overflow-hidden p-5"
        showCloseButton
      >
        <DialogHeader className="shrink-0 pr-10">
          <DialogTitle className="text-lg">
            Filter by sample or group
          </DialogTitle>
        </DialogHeader>
        <Tabs
          className="flex min-h-0 flex-1 flex-col"
          value={activeTab}
          onValueChange={(value) => setActiveTab(value as FilterTab)}
        >
          <TabsList className="mb-3 grid shrink-0 grid-cols-2 gap-0">
            <TabsTrigger className="px-2 py-2 text-xs" value="sample">
              Sample
            </TabsTrigger>
            <TabsTrigger className="px-2 py-2 text-xs" value="sample_group">
              Sample group
            </TabsTrigger>
          </TabsList>
          <TabsContent
            className="min-h-0 flex-1 flex-col gap-3 data-[state=active]:flex"
            value="sample"
          >
            <FilterSearchInput
              placeholder="Search samples..."
              value={sampleSearch}
              onChange={setSampleSearch}
            />
            <FilterOptionList
              emptyText="No samples found."
              hasMore={Boolean(samplePages.hasNextPage)}
              isLoading={
                samplePages.isLoading || samplePages.isFetchingNextPage
              }
              onLoadMore={() => void samplePages.fetchNextPage()}
            >
              {samples.map((sample) => {
                const label = sample.sample_name || sample.sample_id;
                const subtitle = sampleSubtitle(sample);
                return (
                  <FilterOptionButton
                    key={sample.sample_id}
                    selected={pendingSampleIds.includes(sample.sample_id)}
                    subtitle={subtitle}
                    title={label}
                    search={sampleSearch}
                    onClick={() => selectSample(sample.sample_id)}
                  />
                );
              })}
            </FilterOptionList>
            {sampleSearch.trim() ? (
              <Button
                className="w-full justify-start"
                size="sm"
                type="button"
                variant="ghost"
                onClick={() => selectSample(sampleSearch.trim())}
              >
                Use sample ID "{sampleSearch.trim()}"
              </Button>
            ) : null}
            <FilterMenuFooter onClear={clearFilters} onDone={commitFilters} />
          </TabsContent>
          <TabsContent
            className="min-h-0 flex-1 flex-col gap-3 data-[state=active]:flex"
            value="sample_group"
          >
            <FilterSearchInput
              placeholder="Search sample groups..."
              value={sampleGroupSearch}
              onChange={setSampleGroupSearch}
            />
            <button
              className={[
                "flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm transition-colors",
                !pendingSampleGroupIds.length &&
                !pendingSampleIds.length &&
                !pendingRunSampleIds.length
                  ? "border-[#16784a] bg-[#e8f5ee] text-[#145c3a]"
                  : "border-[#d6dee8] bg-white text-[#1f2937] hover:bg-[#f8fafc]",
              ].join(" ")}
              type="button"
              onClick={clearFilters}
            >
              <span className="font-semibold">All samples</span>
            </button>
            <FilterOptionList
              emptyText="No sample groups found."
              hasMore={Boolean(sampleGroupPages.hasNextPage)}
              isLoading={
                sampleGroupPages.isLoading ||
                sampleGroupPages.isFetchingNextPage
              }
              onLoadMore={() => void sampleGroupPages.fetchNextPage()}
            >
              {sampleGroups.map((sampleGroup) => {
                return (
                  <FilterOptionButton
                    key={sampleGroup.sample_set_id}
                    selected={pendingSampleGroupIds.includes(
                      sampleGroup.sample_set_id,
                    )}
                    subtitle={`${sampleGroup.member_count.toLocaleString()} samples`}
                    title={sampleGroup.name}
                    search={sampleGroupSearch}
                    onClick={() => selectSampleGroup(sampleGroup.sample_set_id)}
                  />
                );
              })}
            </FilterOptionList>
            <FilterMenuFooter
              onClear={() => setOpen(false)}
              onDone={commitFilters}
            />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

function TableColumnPickerDialog({
  contracts,
  open,
  selectedColumns,
  onAddAll,
  onOpenChange,
  onSelect,
}: {
  contracts: DataContract[];
  open: boolean;
  selectedColumns: BuilderSeries[];
  onAddAll: (contract: DataContract) => void;
  onOpenChange: (open: boolean) => void;
  onSelect: (contract: DataContract, field: DataContractField) => void;
}) {
  const [search, setSearch] = useState("");
  const groups = useMemo(
    () => filterContractGroups(contracts, search),
    [contracts, search],
  );
  const selected = useMemo(
    () =>
      new Set(
        selectedColumns
          .filter((column) => column.contractId && column.fieldId)
          .map((column) => `${column.contractId}::${column.fieldId}`),
      ),
    [selectedColumns],
  );

  useEffect(() => {
    if (!open) setSearch("");
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[min(720px,90vh)] max-w-[min(760px,94vw)] flex-col overflow-hidden p-5">
        <DialogHeader className="shrink-0 pr-10">
          <DialogTitle>Add table column</DialogTitle>
        </DialogHeader>
        <div className="relative shrink-0">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#758195]" />
          <Input
            autoFocus
            className="pl-9"
            placeholder="Search fields..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {groups.map(({ contract, fields }) => (
            <section
              className="rounded-md border border-[#d9e1ea] bg-white"
              key={contract.data_contract_id}
            >
              <div className="flex items-center justify-between gap-3 border-b border-[#e8edf3] px-3 py-2">
                <div className="min-w-0">
                  <div className="truncate text-xs font-bold uppercase tracking-wide text-[#657082]">
                    {highlightSearchMatch(contract.name.toUpperCase(), search)}
                  </div>
                  <div className="truncate text-xs text-[#758195]">
                    {contract.data_contract_id}
                  </div>
                </div>
                <Button
                  size="sm"
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    onAddAll(contract);
                    onOpenChange(false);
                  }}
                >
                  Add all fields
                </Button>
              </div>
              <div className="grid gap-1 p-2">
                {fields.map((field) => {
                  const isSelected = selected.has(
                    `${contract.data_contract_id}::${field.field_id}`,
                  );
                  return (
                    <button
                      className={[
                        "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-md px-2 py-2.5 text-left text-sm transition-colors",
                        isSelected
                          ? "bg-[#e8f5ee] text-[#16784a]"
                          : "hover:bg-[#f8fafc]",
                      ].join(" ")}
                      key={field.field_id}
                      type="button"
                      onClick={() => onSelect(contract, field)}
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-[15px] font-semibold">
                          {highlightSearchMatch(
                            field.display_name || field.field_id,
                            search,
                          )}
                        </span>
                        <span className="block truncate text-xs text-[#657082]">
                          {highlightSearchMatch(field.field_id, search)}
                        </span>
                      </span>
                      <span className="rounded bg-[#eef3f7] px-2 py-1 text-xs text-[#526071]">
                        {field.field_role === "payload"
                          ? "payload"
                          : field.value_type}
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
        <DialogFooter className="shrink-0 border-t border-[#e8edf3] pt-3">
          <DialogClose asChild>
            <Button type="button" variant="outline">
              Done
            </Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FilterSearchInput({
  placeholder,
  value,
  onChange,
}: {
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#758195]" />
      <Input
        className="pl-9"
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => event.stopPropagation()}
      />
    </div>
  );
}

function FilterOptionList({
  children,
  emptyText,
  hasMore,
  isLoading,
  onLoadMore,
}: {
  children: React.ReactNode;
  emptyText: string;
  hasMore: boolean;
  isLoading: boolean;
  onLoadMore: () => void;
}) {
  const hasItems = Boolean(childrenArray(children).length);
  const handleScroll = (event: UIEvent<HTMLDivElement>) => {
    if (!hasMore || isLoading) return;
    const element = event.currentTarget;
    const remaining =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    if (remaining < 80) onLoadMore();
  };
  return (
    <div
      className="min-h-0 flex-1 overflow-y-auto pr-1"
      onScroll={handleScroll}
    >
      <div className="space-y-1">
        {children}
        {!hasItems && !isLoading ? (
          <div className="rounded-md border border-[#dce3eb] bg-[#f8fafc] px-3 py-4 text-sm text-[#657082]">
            {emptyText}
          </div>
        ) : null}
        {isLoading ? (
          <div className="rounded-md px-3 py-2 text-xs text-[#657082]">
            Loading...
          </div>
        ) : null}
        {hasMore && !isLoading ? (
          <div className="h-8 rounded-md px-3 py-2 text-center text-xs text-[#657082]">
            Scroll for more
          </div>
        ) : null}
      </div>
    </div>
  );
}

function FilterOptionButton({
  search,
  selected,
  subtitle,
  title,
  onClick,
}: {
  search: string;
  selected: boolean;
  subtitle?: string;
  title: string;
  onClick: () => void;
}) {
  return (
    <button
      className={[
        "grid w-full gap-0.5 rounded-md border px-3 py-2 text-left text-sm transition-colors",
        selected
          ? "border-[#16784a] bg-[#e8f5ee] text-[#145c3a]"
          : "border-[#d6dee8] bg-white text-[#1f2937] hover:bg-[#f8fafc]",
      ].join(" ")}
      type="button"
      onClick={onClick}
    >
      <span className="truncate font-semibold">
        {highlightSearchMatch(title, search)}
      </span>
      {subtitle ? (
        <span className="truncate text-xs text-[#657082]">
          {highlightSearchMatch(subtitle, search)}
        </span>
      ) : null}
    </button>
  );
}

function FilterMenuFooter({
  onClear,
  onDone,
}: {
  onClear: () => void;
  onDone: () => void;
}) {
  return (
    <div className="flex items-center justify-end gap-2 border-t border-[#e8edf3] pt-3">
      <Button size="sm" type="button" variant="ghost" onClick={onClear}>
        Clear
      </Button>
      <Button size="sm" type="button" onClick={onDone}>
        Done
      </Button>
    </div>
  );
}

function filterTabForSelection({
  sampleGroupIds,
  sampleIds,
}: {
  runSampleIds: string[];
  sampleGroupIds: string[];
  sampleIds: string[];
}): FilterTab {
  if (sampleIds.length) return "sample";
  if (sampleGroupIds.length) return "sample_group";
  return "sample";
}

function sampleFilterSummary({
  sampleGroup,
  sampleGroupIds,
  sampleIds,
}: {
  runSampleIds: string[];
  sampleGroup: SampleSet | undefined;
  sampleGroupIds: string[];
  sampleIds: string[];
}) {
  if (sampleIds.length === 1) return `Sample ${sampleIds[0]}`;
  if (sampleIds.length > 1) return `${sampleIds.length} samples`;
  if (sampleGroupIds.length === 1) {
    return sampleGroup
      ? `Sample group ${sampleGroup.name}`
      : `Sample group ${sampleGroupIds[0]}`;
  }
  if (sampleGroupIds.length > 1)
    return `${sampleGroupIds.length} sample groups`;
  return "All samples";
}

function childrenArray(children: React.ReactNode) {
  return Array.isArray(children)
    ? children.filter(Boolean)
    : children
      ? [children]
      : [];
}

function toggleString(values: string[], value: string) {
  const normalized = value.trim();
  if (!normalized) return values;
  return values.includes(normalized)
    ? values.filter((item) => item !== normalized)
    : [...values, normalized];
}

function pageNextOffset(lastPage: {
  items: unknown[];
  offset: number;
  total: number;
}) {
  const nextOffset = lastPage.offset + lastPage.items.length;
  return nextOffset < lastPage.total ? nextOffset : undefined;
}

function sampleSubtitle(sample: SampleListItem) {
  const subtitleParts = [
    sample.sample_name && sample.sample_name !== sample.sample_id
      ? sample.sample_id
      : "",
    sample.subject_id ? `Subject ${sample.subject_id}` : "",
    sample.run_count ? `${sample.run_count.toLocaleString()} runs` : "",
    sample.latest_run_name || sample.latest_run_id
      ? `Latest ${sample.latest_run_name || sample.latest_run_id}`
      : "",
  ].filter(Boolean);
  return subtitleParts.join(" · ") || undefined;
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
    if (matchIndex > cursor) parts.push(text.slice(cursor, matchIndex));
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
  return parts;
}

function InsightBuilderControls({
  analysisGrain,
  catalog,
  description,
  resetLabel,
  settings,
  visualization,
  onAnalysisGrainChange,
  onDescriptionRequest,
  onResetBuilder,
  onTemplateSelect,
  onVisualizationChange,
}: {
  analysisGrain: AnalysisGrain;
  catalog: InsightCatalog | undefined;
  description: string;
  resetLabel: string;
  settings?: ReactNode;
  visualization: string;
  onAnalysisGrainChange: (value: AnalysisGrain) => void;
  onDescriptionRequest: () => void;
  onResetBuilder: () => void;
  onTemplateSelect: (value: string) => void;
  onVisualizationChange: (value: string) => void;
}) {
  const templates = templatesFromCatalog(catalog);
  const charts = chartOptionsFromCatalog(catalog);
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const hasDescription = Boolean(description.trim());
  const handleTemplateSelect = (value: string) => {
    onTemplateSelect(value);
    setTemplatesOpen(false);
  };
  return (
    <section className="shrink-0 border-b border-[#dce3eb] pb-1">
      <div className="flex flex-wrap items-end gap-2">
        <div className="w-full max-w-[200px] space-y-0.5">
          <Label>Analyze by</Label>
          <Select
            value={analysisGrain}
            onValueChange={(value) =>
              onAnalysisGrainChange(value as AnalysisGrain)
            }
          >
            <SelectTrigger>
              <AnalyzeByValue
                option={analysisGrainsFromCatalog(catalog).find(
                  (grain) => grain.value === analysisGrain,
                )}
              />
            </SelectTrigger>
            <SelectContent>
              {analysisGrainsFromCatalog(catalog).map((grain) => (
                <SelectItem key={grain.value} value={grain.value}>
                  <span className="flex items-center gap-2">
                    <grain.Icon className="h-4 w-4 shrink-0 text-[#657082]" />
                    <span>{grain.label}</span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="w-full max-w-[200px] space-y-0.5">
          <Label>View as</Label>
          <ChartTypePicker
            charts={charts}
            value={visualization}
            onChange={onVisualizationChange}
          />
        </div>
        <div className="ml-auto flex items-end gap-2">
          {settings}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                aria-label="Insight builder actions"
                className="h-9 w-9 shrink-0 shadow-none focus-visible:ring-0"
                size="icon"
                type="button"
                variant="outline"
              >
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              <DropdownMenuItem onClick={onDescriptionRequest}>
                <Pencil className="h-4 w-4" />
                {hasDescription ? "Edit description" : "Add description"}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setTemplatesOpen(true)}>
                <Grid2X2 className="h-4 w-4" />
                Templates
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={onResetBuilder}>
                <Trash2 className="h-4 w-4" />
                {resetLabel}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      <TemplatePickerDialog
        open={templatesOpen}
        templates={templates}
        onOpenChange={setTemplatesOpen}
        onTemplateSelect={handleTemplateSelect}
      />
    </section>
  );
}

type ChartOption = ReturnType<typeof chartOptionsFromCatalog>[number];
type AnalysisGrainOption = ReturnType<typeof analysisGrainsFromCatalog>[number];
type TemplateOption = ReturnType<typeof templatesFromCatalog>[number];

function AnalyzeByValue({
  option,
}: {
  option: AnalysisGrainOption | undefined;
}) {
  if (!option) return <SelectValue />;
  const GrainIcon = option.Icon;
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <GrainIcon className="h-4 w-4 shrink-0 text-[#657082]" />
      <span className="min-w-0 truncate leading-normal">{option.label}</span>
    </div>
  );
}

function ChartTypePicker({
  charts,
  value,
  onChange,
}: {
  charts: ChartOption[];
  value: string;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement | null>(null);
  const selectedChart =
    charts.find((chart) => chart.value === value) ?? charts[0];
  const SelectedChartIcon = selectedChart?.Icon;
  const groups = groupedChartOptions(charts, search);

  useEffect(() => {
    if (!open) {
      setSearch("");
      return;
    }
    const handle = window.setTimeout(() => searchRef.current?.focus(), 0);
    return () => window.clearTimeout(handle);
  }, [open]);

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button
          className="flex h-9 w-full items-center justify-between rounded-lg border border-[#cfd8e3] bg-white px-3 py-2 text-sm text-[#1d2430] transition-colors hover:border-[#b9c5d2] focus:outline-none focus:ring-0"
          type="button"
        >
          <span className="flex min-w-0 items-center gap-2">
            {SelectedChartIcon ? (
              <SelectedChartIcon className="h-4 w-4 shrink-0 text-[#657082]" />
            ) : null}
            <span className="truncate">{selectedChart?.label ?? value}</span>
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-[#657082]" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[360px] p-2 shadow-none">
        <div className="relative mb-2">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#758195]" />
          <Input
            ref={searchRef}
            aria-label="Search chart types"
            className="h-9 pl-9"
            placeholder="Search chart types..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => event.stopPropagation()}
          />
        </div>
        <div className="max-h-[320px] overflow-y-auto pr-1">
          {groups.map((group) => (
            <div key={group.label} className="pb-1">
              <DropdownMenuLabel className="px-2 py-1 text-[0.68rem]">
                {group.label}
              </DropdownMenuLabel>
              {group.items.map((chart) => {
                const ChartIcon = chart.Icon;
                const selected = chart.value === value;
                return (
                  <DropdownMenuItem
                    key={chart.value}
                    className="justify-between"
                    onClick={() => {
                      onChange(chart.value);
                      setOpen(false);
                    }}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <ChartIcon className="h-4 w-4 shrink-0 text-[#657082]" />
                      <span className="truncate">
                        {highlightSearchMatch(chart.label, search)}
                      </span>
                    </span>
                    {selected ? (
                      <Check className="h-4 w-4 shrink-0 text-[#16784a]" />
                    ) : null}
                  </DropdownMenuItem>
                );
              })}
            </div>
          ))}
          {groups.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-[#657082]">
              No chart types found.
            </div>
          ) : null}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function groupedChartOptions(charts: ChartOption[], search: string) {
  const query = search.trim().toLowerCase();
  const groups = [
    {
      label: "Standard",
      values: new Set([
        "table",
        "bar",
        "stacked_bar",
        "line",
        "area",
        "scatter",
        "histogram",
        "boxplot",
        "box_plot",
        "pie",
        "donut",
        "heatmap",
        "metric",
        "stat",
        "number",
      ]),
    },
    {
      label: "Biology",
      values: new Set(["oncoprint", "lollipop", "volcano", "manhattan"]),
    },
    {
      label: "MultiQC",
      values: new Set(["multiqc_module", "multiqc_section", "qc_summary"]),
    },
  ];
  const assignedValues = new Set(groups.flatMap((group) => [...group.values]));
  return [
    ...groups,
    {
      label: "Other",
      values: new Set(
        charts
          .map((chart) => chart.value)
          .filter((value) => !assignedValues.has(value)),
      ),
    },
  ]
    .map((group) => ({
      label: group.label,
      items: charts.filter((chart) => {
        const matchesGroup = group.values.has(chart.value);
        const matchesSearch =
          !query || chart.label.toLowerCase().includes(query);
        return matchesGroup && matchesSearch;
      }),
    }))
    .filter((group) => group.items.length > 0);
}

function TemplatePickerDialog({
  open,
  templates,
  onOpenChange,
  onTemplateSelect,
}: {
  open: boolean;
  templates: TemplateOption[];
  onOpenChange: (open: boolean) => void;
  onTemplateSelect: (value: string) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[min(560px,88vh)] max-w-[min(560px,94vw)] flex-col overflow-hidden p-5">
        <DialogHeader className="shrink-0 pr-10">
          <DialogTitle>Choose a template</DialogTitle>
        </DialogHeader>
        <div className="min-h-0 overflow-y-auto pr-1">
          <div className="grid gap-2">
            {templates.map((template) => (
              <button
                key={template.value}
                className="flex items-center justify-between rounded-lg border border-[#dce3eb] bg-white px-3 py-3 text-left transition-colors hover:border-[#21a66a] hover:bg-[#f6fbf8] focus:outline-none focus:ring-0"
                type="button"
                onClick={() => onTemplateSelect(template.value)}
              >
                <span className="font-medium text-[#1d2430]">
                  {template.label}
                </span>
                <ChevronDown className="h-4 w-4 -rotate-90 text-[#758195]" />
              </button>
            ))}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function executionConfig(config: Record<string, unknown>) {
  // Title and description are saved with the insight, but they are not needed by
  // the execution endpoint. Dropping them keeps preview cache keys focused on
  // behavior-affecting query/display settings.
  const rest = { ...config };
  delete rest.title;
  delete rest.description;
  return rest;
}

function LinkerStrip({
  catalog,
  linkerKind,
  series,
  onLinkerKindChange,
}: {
  catalog: InsightCatalog | undefined;
  linkerKind: LinkerKind;
  series: BuilderSeries[];
  onLinkerKindChange: (value: LinkerKind) => void;
}) {
  const first = series[0]?.fieldId || "X value";
  const second = series[1]?.fieldId || "Y value";
  return (
    <div className="rounded-md border border-[#dce3eb] bg-[#f8fafc] p-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-[#657082]">
        <span className="font-semibold text-[#1f2937]">{first}</span>
        <span>matched by</span>
        <Select
          value={linkerKind}
          onValueChange={(value) => onLinkerKindChange(value as LinkerKind)}
        >
          <SelectTrigger className="h-8 w-[160px] bg-white">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {linkersFromCatalog(catalog).map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="font-semibold text-[#1f2937]">{second}</span>
      </div>
    </div>
  );
}

function analysisGrainsFromCatalog(catalog: InsightCatalog | undefined) {
  const icons: Record<AnalysisGrain, ComponentType<{ className?: string }>> = {
    file: File,
    feature: Braces,
    run: CirclePlay,
    sample: User,
    subject: Users,
    variant: Dna,
  };
  const fallback = [
    ["sample", "Samples"],
    ["subject", "Subjects"],
    ["run", "Runs"],
    ["feature", "Features"],
    ["variant", "Variants"],
    ["file", "Files"],
  ] as const;
  const items = catalog?.analysis_grains.length
    ? catalog.analysis_grains.map(
        (grain) => [stringConfig(grain.id), stringConfig(grain.label)] as const,
      )
    : fallback;
  return items
    .filter((item): item is readonly [AnalysisGrain, string] =>
      isAnalysisGrain(item[0]),
    )
    .map(([value, label]) => ({
      value,
      label: label || value,
      Icon: icons[value] ?? CircleDot,
    }));
}

function templatesFromCatalog(catalog: InsightCatalog | undefined) {
  const items = catalog?.templates.length
    ? catalog.templates.map(
        (template) =>
          [stringConfig(template.id), stringConfig(template.label)] as const,
      )
    : FALLBACK_TEMPLATES.map(
        (template) => [template.id, template.label] as const,
      );
  return items
    .filter((item) => item[0])
    .map(([value, label]) => ({ value, label: label || value }));
}

const FALLBACK_TEMPLATES = [
  {
    id: "qc_metrics_samples",
    label: "QC metrics across samples",
    description: "Start a sample table from QC contract fields.",
    analysis_grain: "sample",
    visualization: "table",
    linker: { kind: "sample" },
  },
  {
    id: "build_table",
    label: "Build a table",
    description: "Choose identity and contract columns at the selected grain.",
    analysis_grain: "sample",
    visualization: "table",
    linker: { kind: "sample" },
  },
  {
    id: "compare_two_fields",
    label: "Compare two fields",
    description: "Create a two-value scatter matched by sample.",
    analysis_grain: "sample",
    visualization: "scatter",
    linker: { kind: "sample" },
  },
  {
    id: "inspect_one_sample",
    label: "Inspect one sample",
    description: "Start a sample-filtered detail table.",
    analysis_grain: "sample",
    visualization: "table",
    linker: { kind: "sample" },
  },
  {
    id: "explore_feature",
    label: "Explore a gene/feature",
    description: "Start a feature-grain numeric distribution.",
    analysis_grain: "feature",
    visualization: "histogram",
    linker: { kind: "feature" },
  },
  {
    id: "variant_call_table",
    label: "Variant/call table",
    description: "Start a table for variants, calls, or feature states.",
    analysis_grain: "variant",
    visualization: "table",
    linker: { kind: "feature" },
  },
] as const;

function templateDefinition(
  templateId: string,
  catalog: InsightCatalog | undefined,
) {
  return (
    catalog?.templates.find((item) => stringConfig(item.id) === templateId) ??
    FALLBACK_TEMPLATES.find((item) => item.id === templateId)
  );
}

function chartOptionsFromCatalog(catalog: InsightCatalog | undefined) {
  const icons: Record<string, ComponentType<{ className?: string }>> = {
    area: AreaChart,
    bar: BarChart3,
    boxplot: Box,
    box_plot: Box,
    donut: PieChart,
    heatmap: Grid2X2,
    histogram: BarChart2,
    line: LineChart,
    metric: Hash,
    number: Hash,
    pie: PieChart,
    scatter: ChartScatter,
    stacked_bar: BarChart3,
    stat: Hash,
    table: Table2,
  };
  const fallback = [
    ["table", "Table"],
    ["bar", "Bar chart"],
    ["scatter", "Scatter plot"],
    ["line", "Line chart"],
    ["histogram", "Histogram"],
    ["boxplot", "Box plot"],
    ["metric", "Metric"],
  ] as const;
  const items = catalog?.charts.length
    ? catalog.charts.map(
        (chart) => [stringConfig(chart.id), stringConfig(chart.label)] as const,
      )
    : fallback;
  return items
    .filter((item) => item[0])
    .map(([value, label]) => ({
      value,
      label: label || value,
      Icon: icons[value] ?? BarChart3,
    }));
}

function linkersFromCatalog(catalog: InsightCatalog | undefined) {
  const fallback = [
    ["auto", "Auto"],
    ["sample", "Sample"],
    ["run", "Run"],
    ["feature", "Feature"],
    ["entity", "Entity"],
  ] as const;
  const items = catalog?.linkers.length
    ? catalog.linkers.map(
        (linker) =>
          [stringConfig(linker.id), stringConfig(linker.label)] as const,
      )
    : fallback;
  return items
    .filter((item): item is readonly [LinkerKind, string] =>
      isLinkerKind(item[0]),
    )
    .map(([value, label]) => ({ value, label: label || value }));
}

function defaultLinkerForGrain(grain: AnalysisGrain): LinkerKind {
  return (
    {
      sample: "sample",
      subject: "entity",
      run: "run",
      feature: "feature",
      variant: "feature",
      file: "run",
    } satisfies Record<AnalysisGrain, LinkerKind>
  )[grain];
}

function identityColumnsForGrain(grain: AnalysisGrain) {
  return (
    {
      sample: ["sample_id"],
      subject: ["entity_id", "sample_id"],
      run: ["run_id"],
      feature: ["feature_id", "sample_id"],
      variant: ["variant_id", "feature_id", "sample_id"],
      file: ["source_file_id", "run_id", "sample_id"],
    } satisfies Record<AnalysisGrain, string[]>
  )[grain];
}

function identityColumnLabel(column: string) {
  return column
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function needsLinkerStrip(visualization: string, series: BuilderSeries[]) {
  const activeValues = series.filter((item) => item.contractId && item.fieldId);
  return (
    visualization === "scatter" ||
    activeValues.length > 1 ||
    ["line", "area", "stacked_bar", "boxplot"].includes(visualization)
  );
}

function validationWarning(validation: InsightValidation | undefined) {
  const message = validation?.messages.find(
    (item) => stringConfig(item.level) === "error",
  );
  return message ? stringConfig(message.message) : null;
}

function buildContext({
  sampleIds,
  sampleSetIds,
}: {
  runSampleIds: string[];
  sampleIds: string[];
  sampleSetIds: string[];
}) {
  const cleanedSampleIds = uniqueNonEmpty(sampleIds);
  const cleanedSampleSetIds = uniqueNonEmpty(sampleSetIds);
  if (cleanedSampleIds.length) {
    return {
      kind: "sample",
      sample_id: cleanedSampleIds[0],
      sample_ids: cleanedSampleIds.length ? cleanedSampleIds : undefined,
    };
  }
  return {
    kind: "cohort",
    sample_set_id: cleanedSampleSetIds[0],
    sample_set_ids: cleanedSampleSetIds.length
      ? cleanedSampleSetIds
      : undefined,
  };
}

function buildResultPolicy({
  mode,
  randomSeed,
  rowLimit,
}: {
  mode: ResultPolicyMode;
  randomSeed: string;
  rowLimit: number;
}) {
  const limit = mode === "preview" ? 1000 : rowLimit;
  return {
    mode,
    limit,
    seed: mode === "random_sample" ? randomSeed || "goodomics" : undefined,
  };
}

function buildConfig({
  title,
  description,
  analysisGrain,
  sampleSetIds,
  sampleIds,
  runSampleIds,
  queryMode,
  seriesItems,
  tableColumnItems,
  contracts,
  selectedContract,
  store,
  table,
  visualization,
  linkerKind,
  resultPolicyMode,
  resultLimit,
  randomSeed,
  displayOptions,
  xField,
  yField,
  advancedSql,
}: {
  title: string;
  description: string;
  analysisGrain: AnalysisGrain;
  sampleSetIds: string[];
  sampleIds: string[];
  runSampleIds: string[];
  queryMode: QueryMode;
  seriesItems: BuilderSeries[];
  tableColumnItems: BuilderSeries[];
  contracts: DataContract[];
  selectedContract: DataContract | undefined;
  store: Store;
  table: string;
  visualization: string;
  linkerKind: LinkerKind;
  resultPolicyMode: ResultPolicyMode;
  resultLimit: number;
  randomSeed: string;
  displayOptions: DisplayOptions;
  xField: string;
  yField: string;
  advancedSql: string;
}) {
  // This is the main compiler from editable form state to the persisted
  // Goodomics insight template. Keep it in lockstep with server/insights.py.
  const context = buildContext({
    runSampleIds,
    sampleIds,
    sampleSetIds,
  });
  const resultPolicy = buildResultPolicy({
    mode: resultPolicyMode,
    randomSeed,
    rowLimit: resultLimit,
  });
  if (queryMode === "contract") {
    const sourceItems =
      visualization === "table" ? tableColumnItems : seriesItems;
    const activeSeries = sourceItems.filter(
      (item) => item.contractId && item.fieldId,
    );
    const firstSeries = activeSeries[0];
    const contractId = firstSeries?.contractId ?? "";
    const firstFieldId = firstSeries?.fieldId ?? "";
    const entity = analysisGrain;
    const identityColumns = identityColumnsForGrain(analysisGrain);
    const query: Record<string, unknown> = {
      // Contract mode targets a semantic data_contract_id. The server resolves the
      // backing analytics table and field metadata from that contract.
      source: { kind: "data_contract", data_contract_id: contractId },
      fields: activeSeries.map((item) => item.fieldId),
      entity,
      measures: activeSeries.map((item, index) => ({
        field: item.fieldId,
        aggregation: item.aggregation || "raw",
        label: seriesLabel(contracts, item, index),
      })),
      limit: resultPolicy.limit,
    };
    if (visualization === "table") {
      const fieldAliases = activeSeries.map((item) =>
        safeFieldAlias(item.fieldId),
      );
      query.dimensions = identityColumns;
      query.columns = [...identityColumns, ...fieldAliases];
      query.measures = [];
      return {
        version: 1,
        title,
        description,
        analysis_grain: analysisGrain,
        context,
        visualization,
        query,
        series: [],
        table_columns: [
          ...identityColumns.map((column) => ({
            column_id: column,
            kind: "identity",
            column,
            label: identityColumnLabel(column),
          })),
          ...activeSeries.map((item, index) => ({
            column_id: item.id,
            kind: "contract_field",
            contract_id: item.contractId,
            field_id: item.fieldId,
            name: seriesLabel(contracts, item, index),
            label: seriesLabel(contracts, item, index),
            value_mode: "raw",
            result_scope: serializeResultScope(item.resultScope, analysisGrain),
          })),
        ],
        linker: { kind: linkerKind },
        filters: [],
        result_policy: resultPolicy,
        display: displayOptionsConfig(displayOptions),
      };
    }
    if (visualization === "histogram") {
      // Histograms need raw numeric values, not an aggregate measure. The server
      // bins those values into the final ECharts series.
      query.y = safeFieldAlias(firstFieldId);
      query.measures = [];
    }
    if (["pie", "donut"].includes(visualization)) {
      // Pie/donut charts group by the selected field and count rows per value.
      const fieldAlias = safeFieldAlias(firstFieldId);
      query.x = fieldAlias;
      query.dimensions = [fieldAlias].filter(Boolean);
      query.measures = [{ field: "*", aggregation: "count", label: "Count" }];
    }
    if (
      ["bar", "line", "area"].includes(visualization) &&
      activeSeries.length === 1
    ) {
      // Single-value plots should show the selected value by the current
      // Analyze by grain rather than count categories inside the selected field.
      query.x = identityColumns[0];
      query.y = safeFieldAlias(firstFieldId);
      query.columns = [identityColumns[0], safeFieldAlias(firstFieldId)].filter(
        Boolean,
      );
      query.measures = [];
    }
    if (
      ["bar", "stacked_bar"].includes(visualization) &&
      activeSeries.length >= 2
    ) {
      // Two-series bars use the second series as the group and the first as the
      // value column, matching the pivoted contract query shape.
      query.x = safeFieldAlias(activeSeries[1].fieldId);
      query.y = safeFieldAlias(activeSeries[0].fieldId);
      query.measures = [];
    }
    if (visualization === "table") {
      // Table previews should show raw contract values rather than aggregated
      // measures.
      query.columns = [safeFieldAlias(firstFieldId)].filter(Boolean);
      query.measures = [];
    }
    if (visualization === "scatter" && activeSeries.length >= 2) {
      // Scatter needs two aligned raw value columns from the contract query.
      query.x = safeFieldAlias(activeSeries[0].fieldId);
      query.y = safeFieldAlias(activeSeries[1].fieldId);
      query.measures = [];
    }
    if (
      ["line", "area"].includes(visualization) &&
      activeSeries.length === 1 &&
      selectedContract?.fields.find((field) => field.field_id === firstFieldId)
        ?.value_type === "numeric"
    ) {
      // A lone numeric series should plot the raw observations in their natural
      // row order instead of collapsing into one aggregate value.
      query.y = safeFieldAlias(firstFieldId);
      query.columns = [safeFieldAlias(firstFieldId)].filter(Boolean);
      query.dimensions = [];
      query.measures = [];
    }
    return {
      version: 1,
      title,
      description,
      analysis_grain: analysisGrain,
      context,
      visualization,
      query,
      series: activeSeries.map((item, index) => ({
        series_id: item.id,
        contract_id: item.contractId,
        field_id: item.fieldId,
        name: seriesLabel(contracts, item, index),
        aggregation: item.aggregation || "raw",
        color: item.color,
        filters: normalizedSeriesFilters(item),
        result_scope: serializeResultScope(item.resultScope, analysisGrain),
      })),
      linker: { kind: linkerKind },
      filters: [],
      result_policy: resultPolicy,
      display: {
        colors: seriesColorMap(contracts, activeSeries),
        ...displayOptionsConfig(displayOptions),
      },
    };
  }
  const query: Record<string, unknown> = {
    // Table mode is the escape hatch: it targets a physical catalog/analytics
    // table and uses the generic builder query compiler on the server.
    source: { store, table },
    dimensions: xField ? [xField] : [],
    measures: [
      {
        field: "value",
        aggregation: "raw",
        label: "Value",
      },
    ],
    limit: resultPolicy.limit,
  };
  if (advancedSql.trim()) query.sql = advancedSql.trim();
  if (visualization === "scatter" || visualization === "heatmap") {
    // Scatter/heatmap use explicit x/y instead of grouped dimensions.
    query.x = xField;
    query.y = yField;
  }
  if (visualization === "histogram") {
    // Table-mode histograms also need raw values so the preview can bin them.
    const valueField = yField || xField;
    query.columns = valueField ? [valueField] : [];
    query.measures = [];
    query.dimensions = [];
    query.y = valueField;
  }
  if (visualization === "table") {
    // Table mode tables should show selected columns without aggregation.
    query.columns = [xField, yField].filter(Boolean);
    query.measures = [];
    query.dimensions = [];
  }
  return {
    version: 1,
    title,
    description,
    analysis_grain: analysisGrain,
    context,
    visualization,
    query,
    series: query.measures,
    linker: { kind: linkerKind },
    filters: [],
    result_policy: resultPolicy,
    display: displayOptionsConfig(displayOptions),
  };
}

function parseSavedSeries(value: unknown, fallbackContractId: string) {
  if (!Array.isArray(value)) return [];
  return value
    .filter(isRecord)
    .map((item, index) => {
      const contractId =
        stringConfig(item.contract_id) ||
        stringConfig(item.data_contract_id) ||
        fallbackContractId;
      const fieldId = stringConfig(item.field_id) || stringConfig(item.field);
      if (!contractId || !fieldId) return null;
      return {
        id:
          stringConfig(item.series_id) ||
          stringConfig(item.column_id) ||
          `series-${index}`,
        contractId,
        fieldId,
        aggregation: stringConfig(item.aggregation) || "raw",
        name: stringConfig(item.name) || stringConfig(item.label),
        color:
          stringConfig(item.color) || CHART_COLORS[index % CHART_COLORS.length],
        filters: parseSavedFilters(item.filters),
        resultScope: parseSavedResultScope(item.result_scope),
      } satisfies BuilderSeries;
    })
    .filter((item): item is BuilderSeries => Boolean(item));
}

function parseSavedFilters(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((item, index) => ({
    id: stringConfig(item.id) || `filter-${index}`,
    field: stringConfig(item.field),
    operator: stringConfig(item.operator) || stringConfig(item.op) || "eq",
    value: stringConfig(item.value),
  }));
}

function serializeResultScope(
  scope: ResultScope,
  analysisGrain: AnalysisGrain,
) {
  return {
    selection:
      analysisGrain === "run" &&
      scope.selection === "latest_successful_per_sample"
        ? "all_eligible_runs"
        : scope.selection,
    analysis_type_ids: scope.analysisTypeIds,
    method_ids: scope.methodIds,
    method_versions: scope.methodVersions,
    run_ids: scope.runIds,
    statuses: scope.statuses,
    started_after: scope.startedAfter || undefined,
    ended_before: scope.endedBefore || undefined,
    run_contract_ids: scope.runContractIds,
  };
}

function parseSavedResultScope(value: unknown): ResultScope {
  const fallback = defaultResultScope();
  if (!isRecord(value)) return fallback;
  const selection = stringConfig(value.selection);
  return {
    ...fallback,
    selection: [
      "latest_successful_per_sample",
      "specific_methods",
      "specific_versions",
      "specific_runs",
      "pinned_results",
    ].includes(selection)
      ? (selection as ResultScope["selection"])
      : fallback.selection,
    analysisTypeIds: stringArrayConfig(value.analysis_type_ids),
    methodIds: stringArrayConfig(value.method_ids),
    methodVersions: stringArrayConfig(value.method_versions),
    runIds: stringArrayConfig(value.run_ids),
    statuses: stringArrayConfig(value.statuses),
    startedAfter: stringConfig(value.started_after),
    endedBefore: stringConfig(value.ended_before),
    runContractIds: stringArrayConfig(value.run_contract_ids),
  };
}

function parseAnalysisGrain(value: unknown): AnalysisGrain {
  const grain = stringConfig(value);
  return isAnalysisGrain(grain) ? grain : "sample";
}

function parseLinkerKind(value: unknown): LinkerKind {
  const kind = stringConfig(value);
  return isLinkerKind(kind) ? kind : "auto";
}

function parseResultPolicyMode(value: unknown): ResultPolicyMode {
  const mode = stringConfig(value);
  return isResultPolicyMode(mode) ? mode : "preview";
}

function isAnalysisGrain(value: string): value is AnalysisGrain {
  return ["sample", "subject", "run", "feature", "variant", "file"].includes(
    value,
  );
}

function isLinkerKind(value: string): value is LinkerKind {
  return ["auto", "sample", "run", "feature", "entity"].includes(value);
}

function isResultPolicyMode(value: string): value is ResultPolicyMode {
  return [
    "preview",
    "more_rows",
    "random_sample",
    "all_rows",
    "export_full_data",
  ].includes(value);
}

function stringConfig(value: unknown) {
  return typeof value === "string" ? value : "";
}

function stringArrayConfig(value: unknown, fallback?: unknown) {
  const values = Array.isArray(value) ? value : [fallback];
  return uniqueNonEmpty(
    values.filter((item): item is string => typeof item === "string"),
  );
}

function uniqueNonEmpty(values: string[]) {
  return Array.from(
    new Set(values.map((value) => value.trim()).filter(Boolean)),
  );
}

function numberConfig(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function filterInsights(insights: SavedInsight[], search: string) {
  // Search stays client-side because the insight list is small and already
  // loaded for the page.
  const normalized = search.trim().toLowerCase();
  if (!normalized) return insights;
  return insights.filter((insight) =>
    [insight.name, insight.description, insight.insight_id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalized)),
  );
}

function parseSource(
  value: unknown,
):
  | { kind: "contract"; dataContractId: string }
  | { kind: "table"; store: Store; table: string } {
  // Saved configs may come from the contract builder, table builder, or older
  // store.table strings. Normalize them into the two editor modes.
  if (isRecord(value)) {
    if (value.kind === "data_contract") {
      return {
        kind: "contract",
        dataContractId:
          typeof value.data_contract_id === "string"
            ? value.data_contract_id
            : "",
      };
    }
    return {
      kind: "table",
      store: value.store === "catalog" ? "catalog" : "analytics",
      table: typeof value.table === "string" ? value.table : "",
    };
  }
  if (typeof value === "string" && value.includes(".")) {
    const [store, table] = value.split(".", 2);
    return {
      kind: "table",
      store: store === "catalog" ? "catalog" : "analytics",
      table,
    };
  }
  return {
    kind: "table",
    store: "analytics",
    table: typeof value === "string" ? value : "",
  };
}

function firstString(
  value: unknown,
  list: unknown,
  fallback: string | undefined,
) {
  // Helper for reading saved configs where x/y may be strings while dimensions
  // and fields are arrays.
  if (typeof value === "string") return value;
  if (Array.isArray(list) && typeof list[0] === "string") return list[0];
  return fallback ?? "";
}
