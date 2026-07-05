import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  createInsight,
  executeInsight,
  getInsightCatalog,
  listInsights,
  listProjectDatabaseTables,
  listProjectDataProfiles,
  listProjectSamples,
  listReports,
  listSampleSets,
  patchInsight,
  validateInsightConfig,
  type DataProfile,
  type DatabaseTable,
  type InsightCatalog,
  type InsightValidation,
  type SampleListItem,
  type SavedInsight,
} from "../api";
import { InsightBuilderHeader } from "../components/insights/InsightBuilderHeader";
import { InsightPreviewPanel } from "../components/insights/InsightPreviewPanel";
import {
  InsightSeriesEditor,
  blankSeries,
  fieldForSeries,
  profileSeries,
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
  DelayedHoverPopover,
  Input,
  Label,
  Page,
  SearchSuggestionInput,
  type SearchSuggestionOption,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
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
type QueryMode = "profile" | "table";
type ContextKind = "cohort" | "sample";
type BuilderMode =
  | "profile_metrics"
  | "comparison"
  | "sample_detail"
  | "variant_table";
type LinkerKind = "auto" | "sample" | "run_sample" | "run" | "feature" | "entity";
type ResultPolicyMode =
  | "preview"
  | "more_rows"
  | "random_sample"
  | "all_rows"
  | "export_full_data";

/** Insight index and builder page for saved charts, metrics, and tables. */
export function InsightsPage({ projectId }: { projectId: string }) {
  // These queries feed both the list view and the builder. Profiles provide the
  // semantic route; database tables provide the lower-level escape hatch.
  const insights = useQuery({
    queryKey: ["insights", projectId],
    queryFn: () => listInsights(projectId),
  });
  const tables = useQuery({
    queryKey: ["database-tables", projectId],
    queryFn: () => listProjectDatabaseTables(projectId),
  });
  const profiles = useQuery({
    queryKey: ["data-profiles", projectId],
    queryFn: () => listProjectDataProfiles(projectId),
  });
  const reports = useQuery({
    queryKey: ["reports", projectId],
    queryFn: () => listReports(projectId),
  });
  const catalog = useQuery({
    queryKey: ["insight-catalog"],
    queryFn: getInsightCatalog,
  });
  const sampleSets = useQuery({
    queryKey: ["sample-sets", projectId, "cohort"],
    queryFn: () => listSampleSets(projectId, "cohort"),
  });
  const [mode, setMode] = useState<InsightMode>("list");
  const [search, setSearch] = useState("");
  const [selectedInsightId, setSelectedInsightId] = useState<string | null>(
    null,
  );
  const selectedInsight = insights.data?.find(
    (insight) => insight.insight_id === selectedInsightId,
  );
  const [title, setTitle] = useState("New insight");
  const [description, setDescription] = useState("");
  const [contextKind, setContextKind] = useState<ContextKind>("cohort");
  const [sampleSetId, setSampleSetId] = useState("");
  const [sampleId, setSampleId] = useState("");
  const [runSampleId, setRunSampleId] = useState("");
  const [builderMode, setBuilderMode] =
    useState<BuilderMode>("profile_metrics");
  const [queryMode, setQueryMode] = useState<QueryMode>("profile");
  const [profileId, setProfileId] = useState("");
  const [fieldId, setFieldId] = useState("");
  const [series, setSeries] = useState<BuilderSeries[]>([
    blankSeries(0, "", ""),
  ]);
  const [store, setStore] = useState<Store>("analytics");
  const [table, setTable] = useState("");
  const [visualization, setVisualization] = useState("bar");
  const [linkerKind, setLinkerKind] = useState<LinkerKind>("auto");
  const [resultPolicyMode, setResultPolicyMode] =
    useState<ResultPolicyMode>("preview");
  const [resultLimit, setResultLimit] = useState(5000);
  const [randomSeed, setRandomSeed] = useState("goodomics");
  const [displayOptions, setDisplayOptions] = useState<DisplayOptions>(
    DEFAULT_DISPLAY_OPTIONS,
  );
  const [xField, setXField] = useState("");
  const [yField, setYField] = useState("");
  const [aggregation, setAggregation] = useState("count");
  const [advancedSql, setAdvancedSql] = useState("");
  const availableTables = tables.data ?? [];
  const availableProfiles = profiles.data ?? [];
  const selectedProfile = availableProfiles.find(
    (candidate) => candidate.data_profile_id === profileId,
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
  const selectBuilderMode = (next: BuilderMode) => {
    setBuilderMode(next);
    setContextKind(next === "sample_detail" ? "sample" : "cohort");
    setQueryMode("profile");
    if (next === "sample_detail" || next === "variant_table") {
      setVisualization("table");
      return;
    }
    if (next === "comparison") {
      setVisualization("scatter");
      return;
    }
    setVisualization("bar");
  };
  const selectProfileField = ({
    fieldId: nextFieldId,
    profileId: nextProfileId,
  }: {
    profileId: string;
    fieldId: string;
  }) => {
    setQueryMode("profile");
    setProfileId(nextProfileId);
    setFieldId(nextFieldId);
  };
  const selectSqlSource = (selection: SqlSourceSelection) => {
    setBuilderMode("variant_table");
    setContextKind("cohort");
    setQueryMode("table");
    setVisualization("table");
    setStore(selection.store);
    setTable(selection.table);
    setXField(selection.xField);
    setYField(selection.yField);
  };

  useEffect(() => {
    // URL parameters are only an entry affordance from other dashboard pages.
    // Once consumed, clear them so normal builder edits do not keep rewriting
    // browser history or reopening the same insight on refresh.
    const params = new URLSearchParams(window.location.search);
    if (params.get("new") === "1") {
      setSelectedInsightId(null);
      setTitle("New insight");
      setDescription("");
      setContextKind("cohort");
      setSampleSetId("");
      setSampleId("");
      setRunSampleId("");
      setBuilderMode("profile_metrics");
      setVisualization("bar");
      setLinkerKind("auto");
      setResultPolicyMode("preview");
      setResultLimit(5000);
      setRandomSeed("goodomics");
      setDisplayOptions(DEFAULT_DISPLAY_OPTIONS);
      setAdvancedSql("");
      setQueryMode("profile");
      setSeries([blankSeries(0, "", "")]);
      setMode("detail");
      window.history.replaceState(null, "", window.location.pathname);
      return;
    }
    const insightId = params.get("insight");
    if (!insightId) return;
    setSelectedInsightId(insightId);
    setMode("detail");
    window.history.replaceState(null, "", window.location.pathname);
  }, []);

  useEffect(() => {
    if (sampleSetId || (sampleSets.data ?? []).length === 0) return;
    setSampleSetId(sampleSets.data?.[0]?.sample_set_id ?? "");
  }, [sampleSetId, sampleSets.data]);

  useEffect(() => {
    // Seed a profile-first insight with the first useful data profile. The
    // profile picker remains the source of truth after the user makes a choice.
    if (profileId || availableProfiles.length === 0) return;
    const preferred =
      availableProfiles.find((candidate) => candidate.fields.length > 0) ??
      availableProfiles[0];
    setProfileId(preferred.data_profile_id);
    const defaultField =
      preferred.fields.find((field) => field.value_type === "numeric")
        ?.field_id ??
      preferred.fields[0]?.field_id ??
      "";
    setFieldId(defaultField);
    setSeries((current) =>
      current.map((item, index) =>
        index === 0 && !item.profileId
          ? {
              ...item,
              profileId: preferred.data_profile_id,
              fieldId: defaultField,
            }
          : item,
      ),
    );
  }, [availableProfiles, profileId]);

  useEffect(() => {
    // When the selected profile changes, choose a numeric field by default so
    // chart previews start from a likely-valid metric.
    if (!selectedProfile || fieldId) return;
    const defaultField =
      selectedProfile.fields.find((field) => field.value_type === "numeric")
        ?.field_id ??
      selectedProfile.fields[0]?.field_id ??
      "";
    setFieldId(defaultField);
  }, [fieldId, selectedProfile]);

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
    if (queryMode !== "profile" || visualization !== "scatter") {
      return;
    }
    setSeries((current) =>
      current.length >= 2
        ? current
        : [
            ...current,
            blankSeries(current.length, current[0]?.profileId ?? profileId, ""),
          ],
    );
  }, [profileId, queryMode, visualization]);

  useEffect(() => {
    // Profiles can arrive after the series state is initialized. Fill any
    // profile-only series with its default field once metadata is available.
    if (queryMode !== "profile" || availableProfiles.length === 0) return;
    setSeries((current) =>
      current.map((item) =>
        item.profileId && !item.fieldId
          ? profileSeries(item.profileId, availableProfiles, item)
          : item,
      ),
    );
  }, [availableProfiles, queryMode]);

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
    setVisualization(String(config.visualization ?? "bar"));
    setSampleSetId(stringConfig(context.sample_set_id));
    setSampleId(stringConfig(context.sample_id));
    setRunSampleId(stringConfig(context.run_sample_id));
    const parsedBuilderMode = parseBuilderMode(config.mode, source.kind);
    setBuilderMode(parsedBuilderMode);
    setContextKind(
      context.kind === "sample" || parsedBuilderMode === "sample_detail"
        ? "sample"
        : "cohort",
    );
    setLinkerKind(parseLinkerKind(linker.kind));
    setResultPolicyMode(parseResultPolicyMode(resultPolicy.mode));
    setResultLimit(numberConfig(resultPolicy.limit, 5000));
    setRandomSeed(stringConfig(resultPolicy.seed) || "goodomics");
    setDisplayOptions(readDisplayOptions(config));
    setQueryMode(source.kind);
    if (source.kind === "profile") {
      setProfileId(source.dataProfileId);
      const selectedField = firstString(query.y, query.fields, "");
      const savedSeries = parseSavedSeries(config.series, source.dataProfileId);
      setFieldId(selectedField || savedSeries[0]?.fieldId || "");
      setSeries(
        savedSeries.length
          ? savedSeries
          : [
              {
                ...blankSeries(0, source.dataProfileId, selectedField),
                aggregation,
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
        contextKind,
        sampleSetId,
        sampleId,
        runSampleId,
        builderMode,
        queryMode,
        seriesItems: series,
        profiles: availableProfiles,
        selectedProfile,
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
        aggregation,
        advancedSql,
      }),
    [
      advancedSql,
      aggregation,
      availableProfiles,
      builderMode,
      contextKind,
      description,
      displayOptions,
      fieldId,
      linkerKind,
      profileId,
      queryMode,
      randomSeed,
      resultLimit,
      resultPolicyMode,
      series,
      selectedProfile,
      sampleId,
      sampleSetId,
      store,
      table,
      title,
      visualization,
      runSampleId,
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
    queryKey: ["insight-preview", projectId, selectedInsightId, previewConfig],
    queryFn: () =>
      executeInsight({
        insightId: selectedInsightId ?? undefined,
        projectId,
        config: previewConfig,
      }),
    enabled:
      mode === "detail" &&
      (queryMode === "profile"
        ? series.some((item) => item.profileId && item.fieldId)
        : Boolean(table || advancedSql.trim())),
    retry: false,
  });
  const setupWarning = chartSetupWarning({
    profiles: availableProfiles,
    queryMode,
    series,
    visualization,
  }) ?? validationWarning(validation.data);
  const save = useMutation({
    // Saved insights keep the same config shape that report templates consume,
    // so the dashboard builder and portable YAML/JSON exports stay aligned.
    mutationFn: (continueEditing: boolean) =>
      selectedInsightId
        ? patchInsight(selectedInsightId, { name: title, description, config })
        : createInsight({
            project_id: projectId,
            name: title,
            description,
            config,
          }),
    onSuccess: (saved, continueEditing) => {
      setSelectedInsightId(saved.insight_id);
      setMode(continueEditing ? "detail" : "list");
      void queryClient.invalidateQueries({ queryKey: ["insights", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["reports", projectId] });
      void queryClient.invalidateQueries({
        queryKey: ["insight-preview", projectId, saved.insight_id],
      });
    },
  });

  const openNewInsight = () => {
    // Preserve the currently selected profile/field when starting another
    // insight; this makes repeated chart authoring less jumpy.
    setSelectedInsightId(null);
    setTitle("New insight");
    setDescription("");
    setContextKind("cohort");
    setSampleId("");
    setRunSampleId("");
    setBuilderMode("profile_metrics");
    setVisualization("bar");
    setLinkerKind("auto");
    setResultPolicyMode("preview");
    setResultLimit(5000);
    setRandomSeed("goodomics");
    setDisplayOptions(DEFAULT_DISPLAY_OPTIONS);
    setAdvancedSql("");
    setQueryMode("profile");
    setSeries([blankSeries(0, profileId, fieldId)]);
    setMode("detail");
  };

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
          <Button onClick={openNewInsight}>
            <Plus className="h-4 w-4" /> New insight
          </Button>
        </div>
        <AsyncBlock query={insights} empty="No saved insights yet.">
          {(data) => (
            <InsightListTable
              insights={filterInsights(data, search)}
              reportCounts={reportCounts}
              onOpen={(insight) => {
                setSelectedInsightId(insight.insight_id);
                setMode("detail");
              }}
            />
          )}
        </AsyncBlock>
      </Page>
    );
  }

  return (
    <div className="flex h-[calc(100vh-48px)] min-h-0 flex-col gap-4">
      <InsightBuilderHeader
        description={description}
        isSaving={save.isPending}
        title={title}
        onBack={() => setMode("list")}
        onDescriptionChange={setDescription}
        onSave={() => save.mutate(false)}
        onSaveContinue={() => save.mutate(true)}
        onTitleChange={setTitle}
      />
      <InsightContextTabs
        builderMode={builderMode}
        catalog={catalog.data}
        contextKind={contextKind}
        projectId={projectId}
        runSampleId={runSampleId}
        sampleId={sampleId}
        onBuilderModeChange={selectBuilderMode}
        onRunSampleIdChange={setRunSampleId}
        onSampleIdChange={setSampleId}
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="min-h-0 space-y-4 overflow-y-auto">
          <Card className="mt-0">
            <CardContent className="space-y-3">
              <InsightSeriesEditor
                advancedSql={advancedSql}
                profiles={availableProfiles}
                series={series}
                setSeries={setSeries}
                sourceKind={queryMode}
                store={store}
                table={table}
                tables={availableTables}
                xField={xField}
                yField={yField}
                onAdvancedSqlChange={setAdvancedSql}
                onProfileFieldSelect={selectProfileField}
                onSqlSourceSelect={selectSqlSource}
              />
              {builderMode === "profile_metrics" && selectedProfile ? (
                <Button
                  className="w-full justify-center"
                  variant="outline"
                  onClick={() =>
                    setSeries(
                      selectedProfile.fields
                        .filter((field) => field.value_type === "numeric")
                        .map((field, index) => ({
                          ...blankSeries(
                            index,
                            selectedProfile.data_profile_id,
                            field.field_id,
                          ),
                        })),
                    )
                  }
                >
                  Add all numeric fields
                </Button>
              ) : null}
              {queryMode === "profile" ? (
                <div className="rounded-md border border-[#dce3eb] bg-[#f8fafc] p-3 text-xs text-[#657082]">
                  {seriesGuidance(visualization)}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card className="mt-0">
            <CardContent className="space-y-4">
              <Label>Options</Label>
            {builderMode === "profile_metrics" ? (
              <Field label="Cohort">
                <Select value={sampleSetId} onValueChange={setSampleSetId}>
                  <SelectTrigger>
                    <SelectValue placeholder="All samples" />
                  </SelectTrigger>
                  <SelectContent>
                    {(sampleSets.data ?? []).map((sampleSet) => (
                      <SelectItem
                        key={sampleSet.sample_set_id}
                        value={sampleSet.sample_set_id}
                      >
                        {sampleSet.name} ({sampleSet.member_count})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            ) : null}
            <Field label="Aggregation">
              <Select value={aggregation} onValueChange={setAggregation}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {["count", "sum", "avg", "min", "max"].map((item) => (
                    <SelectItem key={item} value={item}>
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Matched by">
              <Select
                value={linkerKind}
                onValueChange={(value) => setLinkerKind(value as LinkerKind)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {linkersFromCatalog(catalog.data).map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <DataSizeControls
              mode={resultPolicyMode}
              randomSeed={randomSeed}
              rowLimit={resultLimit}
              onModeChange={setResultPolicyMode}
              onRandomSeedChange={setRandomSeed}
              onRowLimitChange={setResultLimit}
            />
            </CardContent>
          </Card>
        </div>

        <InsightPreviewPanel
          catalog={catalog.data}
          config={previewConfig}
          displayOptions={displayOptions}
          error={preview.error instanceof Error ? preview.error : null}
          isCached={Boolean(preview.data?.cached)}
          result={preview.data}
          setupWarning={setupWarning}
          title={title}
          visualization={visualization}
          onDisplayOptionsChange={setDisplayOptions}
          onVisualizationChange={setVisualization}
        />
      </div>
    </div>
  );
}

function safeFieldAlias(value: string) {
  // The server can return safe aliases for profile fields with punctuation. Use
  // the same aliasing rule when building x/y fields and color map keys.
  return value
    .replace(/[^a-zA-Z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}

function seriesGuidance(visualization: string) {
  // Guidance mirrors the config-shaping rules in buildConfig so users see why a
  // particular chart asks for one series, two series, or numeric fields.
  if (visualization === "histogram") {
    return "Each series is plotted as its own colored distribution.";
  }
  if (visualization === "scatter") {
    return "Scatter plots use the first two series as aligned X and Y values.";
  }
  if (["bar", "stacked_bar"].includes(visualization)) {
    return "With one series, bars count unique values. Add a second series to plot a value by group.";
  }
  if (["line", "area", "bar", "stacked_bar"].includes(visualization)) {
    return "Use sample or run creation date fields in advanced table mode for added-over-time charts.";
  }
  return "Add one or more colored series from profile fields, then preview the result.";
}

function chartSetupWarning({
  profiles,
  queryMode,
  series,
  visualization,
}: {
  profiles: DataProfile[];
  queryMode: QueryMode;
  series: BuilderSeries[];
  visualization: string;
}) {
  // Warnings are advisory overlays; the server still validates the executable
  // config and returns concrete errors for invalid queries.
  if (queryMode !== "profile") return null;
  const activeSeries = series.filter((item) => item.profileId && item.fieldId);
  if (activeSeries.length === 0) {
    return "Choose a data profile field to preview this chart.";
  }
  if (visualization === "scatter" && activeSeries.length < 2) {
    return "Scatter plots need two aligned numeric series.";
  }
  if (["histogram", "scatter"].includes(visualization)) {
    const nonNumeric = activeSeries
      .slice(0, visualization === "scatter" ? 2 : activeSeries.length)
      .find((item) => fieldForSeries(profiles, item)?.value_type !== "numeric");
    if (nonNumeric) {
      return `${seriesDisplayName(profiles, nonNumeric)} must be numeric for this chart type.`;
    }
  }
  return null;
}

function seriesColorMap(profiles: DataProfile[], series: BuilderSeries[]) {
  // Store colors under every label the renderer might see: raw field IDs, safe
  // field aliases, display labels, and the generated Count series.
  const entries = series.flatMap((item, index) => {
    const label = seriesLabel(profiles, item, index);
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
  profiles: DataProfile[],
  item: BuilderSeries,
  index: number,
) {
  return (
    item.name ||
    fieldForSeries(profiles, item)?.display_name ||
    item.fieldId ||
    `Series ${index + 1}`
  );
}

/** Label-and-control wrapper used by the insight builder sidebar. */
function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

function SampleSearchInput({
  projectId,
  sampleId,
  onSampleIdChange,
}: {
  projectId: string;
  sampleId: string;
  onSampleIdChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [sampleInput, setSampleInput] = useState(sampleId);
  const [sampleSearch, setSampleSearch] = useState("");
  const lastSelectedIdRef = useRef("");
  const pageSize = 50;
  const samplePages = useInfiniteQuery({
    queryKey: ["project-sample-suggestions", projectId, sampleSearch],
    queryFn: ({ pageParam }) =>
      listProjectSamples({
        projectId,
        limit: pageSize,
        offset: pageParam,
        search: sampleSearch,
      }),
    enabled: open,
    initialPageParam: 0,
    getNextPageParam: (lastPage) => {
      const nextOffset = lastPage.offset + lastPage.items.length;
      return nextOffset < lastPage.total ? nextOffset : undefined;
    },
  });
  const sampleOptions = useMemo(
    () =>
      (samplePages.data?.pages ?? [])
        .flatMap((page) => page.items)
        .map(sampleSuggestionOption),
    [samplePages.data?.pages],
  );

  useEffect(() => {
    if (sampleId === lastSelectedIdRef.current) return;
    setSampleInput(sampleId);
  }, [sampleId]);

  return (
    <SearchSuggestionInput
      emptyText="No samples found."
      hasMore={Boolean(samplePages.hasNextPage)}
      inputValue={sampleInput}
      isLoading={samplePages.isLoading || samplePages.isFetchingNextPage}
      loadMoreText={
        samplePages.isFetchingNextPage ? "Loading more samples..." : "Loading..."
      }
      options={sampleOptions}
      placeholder="Search samples..."
      searchValue={sampleSearch}
      onInputValueChange={(value) => {
        lastSelectedIdRef.current = "";
        setSampleInput(value);
        onSampleIdChange(value);
      }}
      onLoadMore={() => {
        if (samplePages.hasNextPage && !samplePages.isFetchingNextPage) {
          void samplePages.fetchNextPage();
        }
      }}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen);
        if (nextOpen) setSampleSearch("");
      }}
      onSearchValueChange={setSampleSearch}
      onSelect={(option) => {
        lastSelectedIdRef.current = option.id;
        setSampleInput(option.label);
        setSampleSearch(option.label);
        onSampleIdChange(option.id);
      }}
    />
  );
}

function sampleSuggestionOption(sample: SampleListItem): SearchSuggestionOption {
  const label = sample.sample_name || sample.sample_id;
  const subtitleParts = [
    sample.sample_name && sample.sample_name !== sample.sample_id
      ? sample.sample_id
      : "",
    sample.subject_id ? `Subject ${sample.subject_id}` : "",
  ].filter(Boolean);
  return {
    id: sample.sample_id,
    label,
    subtitle: subtitleParts.join(" · ") || undefined,
  };
}

function InsightContextTabs({
  builderMode,
  catalog,
  contextKind,
  projectId,
  runSampleId,
  sampleId,
  onBuilderModeChange,
  onRunSampleIdChange,
  onSampleIdChange,
}: {
  builderMode: BuilderMode;
  catalog: InsightCatalog | undefined;
  contextKind: ContextKind;
  projectId: string;
  runSampleId: string;
  sampleId: string;
  onBuilderModeChange: (value: BuilderMode) => void;
  onRunSampleIdChange: (value: string) => void;
  onSampleIdChange: (value: string) => void;
}) {
  const tabs = builderTabsFromCatalog(catalog);
  return (
    <section className="shrink-0 border-b border-[#dce3eb]">
      <div className="flex min-h-[46px] flex-wrap items-end gap-7 px-1">
        {tabs.map((tab) => {
          const active = tab.value === builderMode;
          return (
            <DelayedHoverPopover
              content={
                <>
                  <div className="mb-1 font-semibold text-[#1f2937]">
                    {tab.label}
                  </div>
                  {tab.description}
                </>
              }
              key={tab.value}
            >
              <button
                className={[
                  "relative h-11 border-b-2 px-0 text-sm font-semibold tracking-normal transition-colors",
                  active
                    ? "border-[#16784a] text-[#16784a]"
                    : "border-transparent text-[#657082] hover:text-[#1f2937]",
                ].join(" ")}
                type="button"
                onClick={() => onBuilderModeChange(tab.value)}
              >
                {tab.label}
              </button>
            </DelayedHoverPopover>
          );
        })}
      </div>
      {contextKind === "sample" ? (
        <div className="flex flex-wrap items-end gap-3 pb-3 pt-2">
          <div className="w-full max-w-[260px] space-y-1.5">
            <Label>Sample</Label>
            <SampleSearchInput
              projectId={projectId}
              sampleId={sampleId}
              onSampleIdChange={onSampleIdChange}
            />
          </div>
          <div className="w-full max-w-[300px] space-y-1.5">
            <Label>Processed sample</Label>
            <Input
              placeholder="run:S1"
              value={runSampleId}
              onChange={(event) => onRunSampleIdChange(event.target.value)}
            />
          </div>
          <div className="pb-2 text-xs text-[#657082]">
            Sample mode uses the same guardrails as sample detail.
          </div>
        </div>
      ) : null}
    </section>
  );
}

function DataSizeControls({
  mode,
  randomSeed,
  rowLimit,
  onModeChange,
  onRandomSeedChange,
  onRowLimitChange,
}: {
  mode: ResultPolicyMode;
  randomSeed: string;
  rowLimit: number;
  onModeChange: (value: ResultPolicyMode) => void;
  onRandomSeedChange: (value: string) => void;
  onRowLimitChange: (value: number) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-2">
      <Field label="Data size">
        <Select
          value={mode}
          onValueChange={(value) => onModeChange(value as ResultPolicyMode)}
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
      </Field>
      {mode === "more_rows" || mode === "random_sample" ? (
        <Field label={mode === "more_rows" ? "Row limit" : "Sample size"}>
          <Input
            inputMode="numeric"
            min={1}
            max={10000}
            type="number"
            value={rowLimit}
            onChange={(event) =>
              onRowLimitChange(clampNumber(event.target.value, 1, 10000))
            }
          />
        </Field>
      ) : null}
      {mode === "random_sample" ? (
        <Field label="Seed">
          <Input
            value={randomSeed}
            onChange={(event) => onRandomSeedChange(event.target.value)}
          />
        </Field>
      ) : null}
    </div>
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

function builderTabsFromCatalog(catalog: InsightCatalog | undefined) {
  const fallback = [
    ["profile_metrics", "Cohort analysis"],
    ["sample_detail", "Sample"],
    ["comparison", "Comparison"],
    ["variant_table", "Table"],
  ] as const;
  const items = catalog?.modes.length
    ? fallback.map(([value, fallbackLabel]) => {
        const mode = catalog.modes.find((item) => stringConfig(item.id) === value);
        return [
          value,
          tabLabel(value, stringConfig(mode?.label) || fallbackLabel),
          tabDescription(value, stringConfig(mode?.description)),
        ] as const;
      })
    : fallback;
  return items
    .map((item) =>
      item.length === 2
        ? ([item[0], item[1], tabDescription(item[0], "")] as const)
        : item,
    )
    .filter((item): item is readonly [BuilderMode, string, string] =>
      isBuilderMode(item[0]),
    )
    .map(([value, label, description]) => ({
      value,
      label: label || value,
      description,
    }));
}

function tabLabel(value: string, fallback: string) {
  if (value === "profile_metrics") return "Cohort analysis";
  if (value === "sample_detail") return "Sample";
  if (value === "variant_table") return "Table";
  return fallback;
}

function tabDescription(value: string, fallback: string) {
  if (value === "profile_metrics") {
    return "Build cohort-level metric panels and distributions from profile fields.";
  }
  if (value === "sample_detail") {
    return "Inspect one sample or processed sample with detail and table views.";
  }
  if (value === "comparison") {
    return "Align two or more values by sample, processed sample, feature, or run.";
  }
  if (value === "variant_table") {
    return "Create table-oriented outputs from profile fields or SQL-backed data.";
  }
  return fallback || "Configure an insight with catalog guardrails.";
}

function linkersFromCatalog(catalog: InsightCatalog | undefined) {
  const fallback = [
    ["auto", "Auto"],
    ["sample", "Sample"],
    ["run_sample", "Processed sample"],
    ["run", "Run"],
    ["feature", "Feature"],
    ["entity", "Entity"],
  ] as const;
  const items = catalog?.linkers.length
    ? catalog.linkers.map((linker) => [
        stringConfig(linker.id),
        stringConfig(linker.label),
      ] as const)
    : fallback;
  return items
    .filter((item): item is readonly [LinkerKind, string] =>
      isLinkerKind(item[0]),
    )
    .map(([value, label]) => ({ value, label: label || value }));
}

function validationWarning(validation: InsightValidation | undefined) {
  const message = validation?.messages.find(
    (item) => stringConfig(item.level) === "error",
  );
  return message ? stringConfig(message.message) : null;
}

function buildContext({
  contextKind,
  runSampleId,
  sampleId,
  sampleSetId,
}: {
  contextKind: ContextKind;
  runSampleId: string;
  sampleId: string;
  sampleSetId: string;
}) {
  return contextKind === "sample"
    ? {
        kind: "sample",
        sample_id: sampleId.trim() || undefined,
        run_sample_id: runSampleId.trim() || undefined,
      }
    : {
        kind: "cohort",
        sample_set_id: sampleSetId || undefined,
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
  contextKind,
  sampleSetId,
  sampleId,
  runSampleId,
  builderMode,
  queryMode,
  seriesItems,
  profiles,
  selectedProfile,
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
  aggregation,
  advancedSql,
}: {
  title: string;
  description: string;
  contextKind: ContextKind;
  sampleSetId: string;
  sampleId: string;
  runSampleId: string;
  builderMode: BuilderMode;
  queryMode: QueryMode;
  seriesItems: BuilderSeries[];
  profiles: DataProfile[];
  selectedProfile: DataProfile | undefined;
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
  aggregation: string;
  advancedSql: string;
}) {
  // This is the main compiler from editable form state to the persisted
  // Goodomics insight template. Keep it in lockstep with server/insights.py.
  const context = buildContext({
    contextKind,
    runSampleId,
    sampleId,
    sampleSetId,
  });
  const resultPolicy = buildResultPolicy({
    mode: resultPolicyMode,
    randomSeed,
    rowLimit: resultLimit,
  });
  if (queryMode === "profile") {
    const activeSeries = seriesItems.filter(
      (item) => item.profileId && item.fieldId,
    );
    const firstSeries = activeSeries[0];
    const profileId = firstSeries?.profileId ?? "";
    const firstFieldId = firstSeries?.fieldId ?? "";
    const entity = selectedProfile?.entity_grain ?? undefined;
    const query: Record<string, unknown> = {
      // Profile mode targets a semantic data_profile_id. The server resolves the
      // backing analytics table and field metadata from that profile.
      source: { kind: "data_profile", data_profile_id: profileId },
      fields: activeSeries.map((item) => item.fieldId),
      entity,
      measures: activeSeries.map((item, index) => ({
        field: item.fieldId,
        aggregation: item.aggregation || aggregation,
        label: seriesLabel(profiles, item, index),
      })),
      limit: resultPolicy.limit,
    };
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
      ["bar", "stacked_bar"].includes(visualization) &&
      activeSeries.length === 1
    ) {
      // A single-series bar chart behaves like a categorical count chart.
      const fieldAlias = safeFieldAlias(firstFieldId);
      query.x = fieldAlias;
      query.dimensions = [fieldAlias].filter(Boolean);
      query.measures = [{ field: "*", aggregation: "count", label: "Count" }];
    }
    if (
      ["bar", "stacked_bar"].includes(visualization) &&
      activeSeries.length >= 2
    ) {
      // Two-series bars use the second series as the group and the first as the
      // value column, matching the pivoted profile query shape.
      query.x = safeFieldAlias(activeSeries[1].fieldId);
      query.y = safeFieldAlias(activeSeries[0].fieldId);
      query.measures = [];
    }
    if (visualization === "table") {
      // Table previews should show raw profile values rather than aggregated
      // measures.
      query.columns = [safeFieldAlias(firstFieldId)].filter(Boolean);
      query.measures = [];
    }
    if (visualization === "scatter" && activeSeries.length >= 2) {
      // Scatter needs two aligned raw value columns from the profile query.
      query.x = safeFieldAlias(activeSeries[0].fieldId);
      query.y = safeFieldAlias(activeSeries[1].fieldId);
      query.measures = [];
    }
    if (
      ["line", "area"].includes(visualization) &&
      activeSeries.length === 1 &&
      selectedProfile?.fields.find((field) => field.field_id === firstFieldId)
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
      context,
      mode: builderMode,
      visualization,
      query,
      series: activeSeries.map((item, index) => ({
        series_id: item.id,
        profile_id: item.profileId,
        field_id: item.fieldId,
        name: seriesLabel(profiles, item, index),
        aggregation: item.aggregation || aggregation,
        color: item.color,
        filters: [],
      })),
      linker: { kind: linkerKind },
      filters: [],
      result_policy: resultPolicy,
      display: {
        colors: seriesColorMap(profiles, activeSeries),
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
        field: aggregation === "count" ? "*" : yField,
        aggregation,
        label: aggregation,
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
    context,
    mode: builderMode,
    visualization,
    query,
    series: query.measures,
    linker: { kind: linkerKind },
    filters: [],
    result_policy: resultPolicy,
    display: displayOptionsConfig(displayOptions),
  };
}

function parseSavedSeries(value: unknown, fallbackProfileId: string) {
  if (!Array.isArray(value)) return [];
  return value
    .filter(isRecord)
    .map((item, index) => {
      const profileId =
        stringConfig(item.profile_id) ||
        stringConfig(item.data_profile_id) ||
        fallbackProfileId;
      const fieldId = stringConfig(item.field_id) || stringConfig(item.field);
      if (!profileId || !fieldId) return null;
      return {
        id: stringConfig(item.series_id) || `series-${index}`,
        profileId,
        fieldId,
        aggregation: stringConfig(item.aggregation) || "avg",
        name: stringConfig(item.name) || stringConfig(item.label),
        color: stringConfig(item.color) || CHART_COLORS[index % CHART_COLORS.length],
      } satisfies BuilderSeries;
    })
    .filter((item): item is BuilderSeries => Boolean(item));
}

function parseBuilderMode(value: unknown, sourceKind: QueryMode): BuilderMode {
  const mode = stringConfig(value);
  if (mode === "advanced_sql") return "variant_table";
  if (isBuilderMode(mode)) return mode;
  return sourceKind === "table" ? "variant_table" : "profile_metrics";
}

function parseLinkerKind(value: unknown): LinkerKind {
  const kind = stringConfig(value);
  return isLinkerKind(kind) ? kind : "auto";
}

function parseResultPolicyMode(value: unknown): ResultPolicyMode {
  const mode = stringConfig(value);
  return isResultPolicyMode(mode) ? mode : "preview";
}

function isBuilderMode(value: string): value is BuilderMode {
  return [
    "profile_metrics",
    "comparison",
    "sample_detail",
    "variant_table",
  ].includes(value);
}

function isLinkerKind(value: string): value is LinkerKind {
  return ["auto", "sample", "run_sample", "run", "feature", "entity"].includes(
    value,
  );
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

function clampNumber(value: string, min: number, max: number) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return min;
  return Math.min(Math.max(parsed, min), max);
}

function stringConfig(value: unknown) {
  return typeof value === "string" ? value : "";
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
  | { kind: "profile"; dataProfileId: string }
  | { kind: "table"; store: Store; table: string } {
  // Saved configs may come from the profile builder, table builder, or older
  // store.table strings. Normalize them into the two editor modes.
  if (isRecord(value)) {
    if (value.kind === "data_profile") {
      return {
        kind: "profile",
        dataProfileId:
          typeof value.data_profile_id === "string"
            ? value.data_profile_id
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
