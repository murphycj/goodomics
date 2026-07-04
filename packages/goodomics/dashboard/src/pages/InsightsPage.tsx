import { useMutation, useQuery } from "@tanstack/react-query";
import { HexColorInput, HexColorPicker } from "react-colorful";
import {
  AreaChart,
  ArrowLeft,
  BarChart2,
  BarChart3,
  Box,
  ChevronDown,
  Check,
  Copy,
  Hash,
  LineChart,
  MoreHorizontal,
  PieChart,
  Plus,
  Save,
  Search,
  ScatterChart,
  Settings2,
  Table2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  createInsight,
  executeInsight,
  listInsights,
  listProjectDatabaseTables,
  listProjectDataProfiles,
  listReports,
  patchInsight,
  type DataProfile,
  type DataProfileField,
  type DatabaseTable,
  type SavedInsight,
} from "../api";
import { InsightListTable } from "../components/reports/InsightListTable";
import { InsightPreview } from "../components/reports/InsightPreview";
import { isRecord, readReportItems } from "../components/reports/reportUtils";
import {
  AsyncBlock,
  Button,
  Card,
  CardContent,
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
} from "../components/ui";
import { CHART_COLORS } from "../lib/chartColors";
import { queryClient } from "../lib/queryClient";

type ChartOption = {
  value: string;
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
};

// Chart options are grouped for the selector UI, but the `value` strings are the
// persisted visualization identifiers understood by the server-side renderer.
const CHART_OPTIONS: { group: string; items: ChartOption[] }[] = [
  {
    group: "Time Series",
    items: [
      {
        value: "line",
        label: "Line chart",
        description: "Trends over time as a continuous line.",
        icon: LineChart,
      },
      {
        value: "area",
        label: "Area chart",
        description: "Trends over time as a shaded area.",
        icon: AreaChart,
      },
      {
        value: "bar",
        label: "Bar chart",
        description: "Values as vertical bars.",
        icon: BarChart3,
      },
      {
        value: "stacked_bar",
        label: "Stacked bar chart",
        description: "Series stacked into vertical bars.",
        icon: BarChart2,
      },
    ],
  },
  {
    group: "Total Value",
    items: [
      {
        value: "metric",
        label: "Metric",
        description: "A headline value.",
        icon: Hash,
      },
      {
        value: "pie",
        label: "Pie chart",
        description: "Proportions of a whole.",
        icon: PieChart,
      },
      {
        value: "table",
        label: "Table",
        description: "Rows and columns.",
        icon: Table2,
      },
    ],
  },
  {
    group: "Distributions",
    items: [
      {
        value: "histogram",
        label: "Histogram",
        description: "Distribution of one or more numeric fields.",
        icon: BarChart2,
      },
      {
        value: "boxplot",
        label: "Box plot",
        description: "Quartiles and outliers.",
        icon: Box,
      },
      {
        value: "scatter",
        label: "Scatter plot",
        description: "Two aligned measures plotted together.",
        icon: ScatterChart,
      },
      {
        value: "heatmap",
        label: "Heatmap",
        description: "Intensity across two dimensions.",
        icon: GridIcon,
      },
    ],
  },
];

const SERIES_COLORS = CHART_COLORS;

type Store = DatabaseTable["store"];
type InsightMode = "list" | "detail";
type QueryMode = "profile" | "table";
type DisplayOptions = {
  showValues: boolean;
  showTrendLines: boolean;
  showLegend: boolean;
  showAnnotations: boolean;
};

const DEFAULT_DISPLAY_OPTIONS: DisplayOptions = {
  showValues: false,
  showTrendLines: false,
  showLegend: true,
  showAnnotations: false,
};

// BuilderSeries is UI state, not the saved insight schema. buildConfig() below
// compiles these editable series cards into query.fields, query.measures, and
// display.colors for execution.
type BuilderSeries = {
  id: string;
  profileId: string;
  fieldId: string;
  aggregation: string;
  name: string;
  color: string;
};

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
  const [queryMode, setQueryMode] = useState<QueryMode>("profile");
  const [profileId, setProfileId] = useState("");
  const [fieldId, setFieldId] = useState("");
  const [series, setSeries] = useState<BuilderSeries[]>([
    blankSeries(0, "", ""),
  ]);
  const [store, setStore] = useState<Store>("analytics");
  const [table, setTable] = useState("");
  const [visualization, setVisualization] = useState("bar");
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

  useEffect(() => {
    // URL parameters are only an entry affordance from other dashboard pages.
    // Once consumed, clear them so normal builder edits do not keep rewriting
    // browser history or reopening the same insight on refresh.
    const params = new URLSearchParams(window.location.search);
    if (params.get("new") === "1") {
      setSelectedInsightId(null);
      setTitle("New insight");
      setDescription("");
      setVisualization("bar");
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
              name:
                preferred.fields.find(
                  (field) => field.field_id === defaultField,
                )?.display_name ?? item.name,
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
    setTitle(selectedInsight.name);
    setDescription(selectedInsight.description ?? "");
    setVisualization(String(config.visualization ?? "bar"));
    setDisplayOptions(readDisplayOptions(config));
    setQueryMode(source.kind);
    if (source.kind === "profile") {
      setProfileId(source.dataProfileId);
      const selectedField = firstString(query.y, query.fields, "");
      setFieldId(selectedField);
      setSeries([
        {
          ...blankSeries(0, source.dataProfileId, selectedField),
          aggregation,
        },
      ]);
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
        queryMode,
        seriesItems: series,
        selectedProfile,
        store,
        table,
        visualization,
        displayOptions,
        xField,
        yField,
        aggregation,
        advancedSql,
      }),
    [
      advancedSql,
      aggregation,
      description,
      displayOptions,
      fieldId,
      profileId,
      queryMode,
      series,
      selectedProfile,
      store,
      table,
      title,
      visualization,
      xField,
      yField,
    ],
  );
  const previewConfig = useMemo(() => executionConfig(config), [config]);
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
  });
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
    setVisualization("bar");
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
      <section className="shrink-0 border-b border-[#dce3eb] pb-4">
        <div className="flex items-center gap-3">
          <Button size="icon" variant="ghost" onClick={() => setMode("list")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <BarChart3 className="h-5 w-5 text-[#16784a]" />
          <Input
            className="h-10 flex-1 text-lg font-semibold"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <div className="flex overflow-hidden rounded-lg shadow-sm">
            <Button
              className="rounded-r-none"
              disabled={save.isPending}
              onClick={() => save.mutate(false)}
            >
              <Save className="h-4 w-4" /> Save
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  aria-label="Save options"
                  className="rounded-l-none border-l border-[#16864f] px-2.5"
                  disabled={save.isPending}
                >
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-[240px]">
                <DropdownMenuItem onClick={() => save.mutate(true)}>
                  <Save className="h-4 w-4" /> Save & continue editing
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        <Input
          className="mt-3"
          placeholder="Enter description (optional)"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </section>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
        <Card className="mt-0 min-h-0 overflow-y-auto">
          <CardContent className="space-y-4">
            <Field label="Query mode">
              <Select
                value={queryMode}
                onValueChange={(value) => setQueryMode(value as QueryMode)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="profile">Data profile</SelectItem>
                  <SelectItem value="table">Advanced table</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            {queryMode === "profile" ? (
              <SeriesEditor
                profiles={availableProfiles}
                series={series}
                setSeries={setSeries}
                visualization={visualization}
              />
            ) : (
              <>
                <Field label="Store">
                  <Select
                    value={store}
                    onValueChange={(value) => setStore(value as Store)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="analytics">
                        DuckDB analytics
                      </SelectItem>
                      <SelectItem value="catalog">SQL catalog</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="Table">
                  <Select value={table} onValueChange={setTable}>
                    <SelectTrigger>
                      <SelectValue placeholder="Choose a table" />
                    </SelectTrigger>
                    <SelectContent>
                      {availableTables
                        .filter((item) => item.store === store)
                        .map((item) => (
                          <SelectItem
                            key={`${item.store}:${item.name}`}
                            value={item.name}
                          >
                            {item.name}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                </Field>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="X / group">
                    <ColumnSelect
                      columns={selectedTable?.columns ?? []}
                      value={xField}
                      onChange={setXField}
                    />
                  </Field>
                  <Field label="Y / value">
                    <ColumnSelect
                      columns={selectedTable?.columns ?? []}
                      value={yField}
                      onChange={setYField}
                    />
                  </Field>
                </div>
              </>
            )}
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
            {queryMode === "profile" ? (
              <div className="rounded-md border border-[#dce3eb] bg-[#f8fafc] p-3 text-xs text-[#657082]">
                {seriesGuidance(visualization)}
              </div>
            ) : null}
            {queryMode === "table" ? (
              <Field label="Advanced SQL">
                <textarea
                  className="min-h-[96px] w-full resize-y rounded-lg border border-[#cfd8e3] bg-white p-2 font-mono text-xs outline-none focus:ring-2 focus:ring-[#21a66a]"
                  placeholder="SELECT ... (optional)"
                  value={advancedSql}
                  onChange={(event) => setAdvancedSql(event.target.value)}
                />
              </Field>
            ) : null}
          </CardContent>
        </Card>

        <Card className="mt-0 min-h-0 overflow-hidden p-0">
          <CardContent className="flex h-full min-h-0 flex-col">
            <div className="flex items-center justify-between border-b border-[#dce3eb] px-4 py-3">
              <div>
                <h2 className="m-0 text-base font-semibold">{title}</h2>
                <p className="m-0 text-xs text-[#657082]">
                  {preview.data?.cached
                    ? "Using cached result"
                    : "Preview result"}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <OptionsMenu
                  options={displayOptions}
                  onChange={setDisplayOptions}
                />
                <ChartTypeSelect
                  value={visualization}
                  onChange={setVisualization}
                />
              </div>
            </div>
            <div className="min-h-0 flex-1 p-4">
              {preview.error ? (
                <div className="rounded-md border border-[#fecaca] bg-[#fff1f2] p-3 text-sm text-[#b42318]">
                  {(preview.error as Error).message}
                </div>
              ) : (
                <InsightPreview
                  config={previewConfig}
                  result={preview.data}
                  setupWarning={setupWarning}
                />
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function blankSeries(
  index: number,
  profileId: string,
  fieldId: string,
): BuilderSeries {
  // IDs only need to be stable within this editing session so React can track
  // added/removed series cards.
  return {
    id: `series-${Date.now()}-${index}-${Math.random().toString(16).slice(2)}`,
    profileId,
    fieldId,
    aggregation: "avg",
    name: "",
    color: SERIES_COLORS[index % SERIES_COLORS.length],
  };
}

function profileSeries(
  profileId: string,
  profiles: DataProfile[],
  current: BuilderSeries,
): BuilderSeries {
  // Prefer numeric fields because most chart types need a numeric measure. If a
  // profile exposes only one field, use that field even when it is categorical.
  const profile = profiles.find(
    (candidate) => candidate.data_profile_id === profileId,
  );
  const field =
    profile?.fields.length === 1
      ? profile.fields[0]
      : profile?.fields.find((candidate) => candidate.value_type === "numeric");
  return {
    ...current,
    profileId,
    fieldId: field?.field_id ?? "",
    name: field?.display_name ?? "",
  };
}

function chartOption(value: string) {
  return (
    CHART_OPTIONS.flatMap((group) => group.items).find(
      (item) => item.value === value,
    ) ?? CHART_OPTIONS[0].items[0]
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

function fieldForSeries(profiles: DataProfile[], series: BuilderSeries) {
  // Resolve the selected profile field so chart-specific validation can use its
  // declared value type.
  return profiles
    .find((profile) => profile.data_profile_id === series.profileId)
    ?.fields.find((field) => field.field_id === series.fieldId);
}

function seriesDisplayName(profiles: DataProfile[], series: BuilderSeries) {
  return (
    series.name ||
    fieldForSeries(profiles, series)?.display_name ||
    series.fieldId ||
    "This field"
  );
}

function seriesColorMap(series: BuilderSeries[]) {
  // Store colors under every label the renderer might see: raw field IDs, safe
  // field aliases, display labels, and the generated Count series.
  const entries = series.flatMap((item, index) => {
    const label = item.name || `Series ${index + 1}`;
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

function GridIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
      viewBox="0 0 24 24"
    >
      <rect height="7" width="7" x="3" y="3" />
      <rect height="7" width="7" x="14" y="3" />
      <rect height="7" width="7" x="3" y="14" />
      <rect height="7" width="7" x="14" y="14" />
    </svg>
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

function SeriesEditor({
  profiles,
  series,
  setSeries,
  visualization,
}: {
  profiles: DataProfile[];
  series: BuilderSeries[];
  setSeries: React.Dispatch<React.SetStateAction<BuilderSeries[]>>;
  visualization: string;
}) {
  // Series cards are intentionally profile-first. The table/SQL escape hatch is
  // handled separately so semantic profile queries stay visually distinct.
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Label>Series</Label>
        <Button
          size="sm"
          variant="outline"
          onClick={() =>
            setSeries((current) => [
              ...current,
              blankSeries(current.length, current[0]?.profileId ?? "", ""),
            ])
          }
        >
          <Plus className="h-4 w-4" /> Series
        </Button>
      </div>
      {series.map((item, index) => {
        const profile = profiles.find(
          (candidate) => candidate.data_profile_id === item.profileId,
        );
        const fields = profile?.fields ?? [];
        const field = fields.find(
          (candidate) => candidate.field_id === item.fieldId,
        );
        return (
          <div
            className="rounded-md border border-[#d6dee8] bg-white p-3 shadow-sm"
            key={item.id}
          >
            <div className="mb-3 grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    aria-label={`Choose color for ${seriesDisplayName(
                      profiles,
                      item,
                    )}`}
                    className="flex h-7 w-7 cursor-pointer items-center justify-center rounded-full border border-black/10 text-xs font-semibold text-white shadow-sm outline-none transition-transform hover:scale-105 focus-visible:ring-2 focus-visible:ring-[#21a66a]"
                    style={{ backgroundColor: item.color }}
                    type="button"
                  >
                    {String.fromCharCode(65 + index)}
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-[244px]">
                  <div className="space-y-3 p-2">
                    <HexColorPicker
                      color={item.color}
                      onChange={(color) =>
                        updateSeries(setSeries, item.id, { color })
                      }
                    />
                    <div className="space-y-1.5">
                      <Label>Hex</Label>
                      <HexColorInput
                        className="flex min-h-[38px] w-full rounded-lg border border-[#cfd8e3] bg-white px-3 py-1 font-mono text-sm uppercase outline-none transition-colors focus:ring-2 focus:ring-[#21a66a]"
                        color={item.color}
                        prefixed
                        onChange={(color) =>
                          updateSeries(setSeries, item.id, { color })
                        }
                      />
                    </div>
                  </div>
                </DropdownMenuContent>
              </DropdownMenu>
              <Input
                aria-label="Series name"
                className="h-9 min-w-0 border-transparent bg-transparent px-2 font-semibold shadow-none hover:border-[#cfd8e3] focus:border-[#cfd8e3]"
                placeholder={field?.display_name || `Series ${index + 1}`}
                value={item.name}
                onChange={(event) =>
                  updateSeries(setSeries, item.id, { name: event.target.value })
                }
              />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button aria-label="Series actions" size="icon" variant="ghost">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="min-w-[180px]">
                  <DropdownMenuItem
                    onClick={() =>
                      setSeries((current) => {
                        const source = current.find(
                          (candidate) => candidate.id === item.id,
                        );
                        if (!source) return current;
                        const copyName =
                          source.name ||
                          field?.display_name ||
                          `Series ${index + 1}`;
                        const duplicate = {
                          ...source,
                          id: `series-${Date.now()}-${current.length}-${Math.random()
                            .toString(16)
                            .slice(2)}`,
                          name: `${copyName} copy`,
                          color: SERIES_COLORS[current.length % SERIES_COLORS.length],
                        };
                        const sourceIndex = current.findIndex(
                          (candidate) => candidate.id === item.id,
                        );
                        return [
                          ...current.slice(0, sourceIndex + 1),
                          duplicate,
                          ...current.slice(sourceIndex + 1),
                        ];
                      })
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
            </div>
            <div className="space-y-2">
              <Select
                value={item.profileId}
                onValueChange={(value) =>
                  setSeries((current) =>
                    current.map((candidate) =>
                      candidate.id === item.id
                        ? profileSeries(value, profiles, candidate)
                        : candidate,
                    ),
                  )
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Data profile" />
                </SelectTrigger>
                <SelectContent>
                  {profiles.map((profile) => (
                    <SelectItem
                      key={profile.data_profile_id}
                      value={profile.data_profile_id}
                    >
                      {profile.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={item.fieldId}
                onValueChange={(value) =>
                  setSeries((current) =>
                    current.map((candidate) =>
                      candidate.id === item.id
                        ? {
                            ...candidate,
                            fieldId: value,
                            name:
                              candidate.name ||
                              fields.find((field) => field.field_id === value)
                                ?.display_name ||
                              candidate.name,
                          }
                        : candidate,
                    ),
                  )
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Field / measure" />
                </SelectTrigger>
                <SelectContent>
                  {fields.map((field) => (
                    <SelectItem key={field.field_id} value={field.field_id}>
                      {field.display_name || field.field_id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={item.aggregation}
                onValueChange={(value) =>
                  updateSeries(setSeries, item.id, { aggregation: value })
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
              <FieldSummary field={field} />
            </div>
          </div>
        );
      })}
    </div>
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

function OptionsMenu({
  options,
  onChange,
}: {
  options: DisplayOptions;
  onChange: React.Dispatch<React.SetStateAction<DisplayOptions>>;
}) {
  const items: { key: keyof DisplayOptions; label: string }[] = [
    { key: "showValues", label: "Show values on series" },
    { key: "showTrendLines", label: "Show trend lines" },
    { key: "showLegend", label: "Show legend" },
    { key: "showAnnotations", label: "Show annotations" },
  ];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost">
          <Settings2 className="h-4 w-4" /> Options{" "}
          <ChevronDown className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel>Display</DropdownMenuLabel>
        {items.map((item) => (
          <DropdownMenuItem
            key={item.key}
            onSelect={(event) => {
              event.preventDefault();
              onChange((current) => ({
                ...current,
                [item.key]: !current[item.key],
              }));
            }}
          >
            <span className="flex h-4 w-4 items-center justify-center rounded border border-[#c7d0dd]">
              {options[item.key] ? <Check className="h-3 w-3" /> : null}
            </span>
            {item.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ChartTypeSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const selected = chartOption(value);
  const Icon = selected.icon;
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-[190px]">
        <div className="flex min-w-0 items-center gap-2">
          <Icon className="h-4 w-4 shrink-0" />
          <span className="truncate">{selected.label}</span>
        </div>
      </SelectTrigger>
      <SelectContent className="max-h-[560px] w-[380px]">
        {CHART_OPTIONS.map((group) => (
          <div key={group.group}>
            <div className="px-3 py-2 text-xs font-bold uppercase tracking-wide text-[#8b95a5]">
              {group.group}
            </div>
            {group.items.map((item) => {
              const ItemIcon = item.icon;
              return (
                <SelectItem key={item.value} value={item.value}>
                  <span className="flex items-start gap-3">
                    <ItemIcon className="mt-0.5 h-4 w-4" />
                    <span>
                      <span className="block font-semibold">{item.label}</span>
                      <span className="block text-xs text-[#657082]">
                        {item.description}
                      </span>
                    </span>
                  </span>
                </SelectItem>
              );
            })}
          </div>
        ))}
      </SelectContent>
    </Select>
  );
}

/** Column picker bound to the currently selected data source table. */
function ColumnSelect({
  columns,
  value,
  onChange,
}: {
  columns: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
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
  );
}

function FieldSummary({ field }: { field: DataProfileField | undefined }) {
  // Profile summaries are compact hints from the catalog, not live query
  // results. They help the user choose fields before running a preview.
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
  // Numeric summaries come from profile metadata and may be absent for fields
  // whose values are strings, booleans, or free-form payloads.
  const min = summary.min;
  const max = summary.max;
  if (typeof min === "number" && typeof max === "number") {
    return `${min.toLocaleString()} to ${max.toLocaleString()}`;
  }
  return null;
}

function topValues(summary: Record<string, unknown>) {
  // Show only the first few categorical examples so field cards stay compact.
  const values = summary.top_values;
  if (!Array.isArray(values) || values.length === 0) return null;
  return values
    .slice(0, 3)
    .map((item) =>
      isRecord(item) && "value" in item ? String(item.value) : String(item),
    )
    .join(", ");
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

function buildConfig({
  title,
  description,
  queryMode,
  seriesItems,
  selectedProfile,
  store,
  table,
  visualization,
  displayOptions,
  xField,
  yField,
  aggregation,
  advancedSql,
}: {
  title: string;
  description: string;
  queryMode: QueryMode;
  seriesItems: BuilderSeries[];
  selectedProfile: DataProfile | undefined;
  store: Store;
  table: string;
  visualization: string;
  displayOptions: DisplayOptions;
  xField: string;
  yField: string;
  aggregation: string;
  advancedSql: string;
}) {
  // This is the main compiler from editable form state to the persisted
  // Goodomics insight template. Keep it in lockstep with server/insights.py.
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
        label: item.name || `Series ${index + 1}`,
      })),
      limit: 1000,
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
      visualization,
      query,
      series: query.measures,
      filters: [],
      display: {
        colors: seriesColorMap(activeSeries),
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
    limit: 1000,
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
    visualization,
    query,
    series: query.measures,
    filters: [],
    display: displayOptionsConfig(displayOptions),
  };
}

function displayOptionsConfig(options: DisplayOptions) {
  return {
    show_values: options.showValues,
    show_trend_lines: options.showTrendLines,
    show_legend: options.showLegend,
    show_annotations: options.showAnnotations,
  };
}

function readDisplayOptions(config: Record<string, unknown>): DisplayOptions {
  if (!isRecord(config.display)) return DEFAULT_DISPLAY_OPTIONS;
  return {
    showValues: Boolean(
      config.display.show_values ?? DEFAULT_DISPLAY_OPTIONS.showValues,
    ),
    showTrendLines: Boolean(
      config.display.show_trend_lines ?? DEFAULT_DISPLAY_OPTIONS.showTrendLines,
    ),
    showLegend: Boolean(
      config.display.show_legend ?? DEFAULT_DISPLAY_OPTIONS.showLegend,
    ),
    showAnnotations: Boolean(
      config.display.show_annotations ?? DEFAULT_DISPLAY_OPTIONS.showAnnotations,
    ),
  };
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
