import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, BarChart3, Plus, RefreshCw, Save, Search, Table2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  createInsight,
  executeInsight,
  listInsights,
  listProjectDatabaseTables,
  patchInsight,
  type DatabaseTable,
  type SavedInsight,
} from "../api";
import { InsightListTable } from "../components/reports/InsightListTable";
import { InsightPreview } from "../components/reports/InsightPreview";
import { isRecord } from "../components/reports/reportUtils";
import {
  AsyncBlock,
  Button,
  Card,
  CardContent,
  Input,
  Label,
  Page,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui";
import { queryClient } from "../lib/queryClient";

const VISUALIZATIONS = [
  "line",
  "area",
  "bar",
  "stacked_bar",
  "scatter",
  "pie",
  "donut",
  "histogram",
  "metric",
  "table",
  "heatmap",
  "boxplot",
] as const;

type Store = DatabaseTable["store"];
type InsightMode = "list" | "detail";

/** Insight index and builder page for saved charts, metrics, and tables. */
export function InsightsPage({ projectId }: { projectId: string }) {
  const insights = useQuery({
    queryKey: ["insights", projectId],
    queryFn: () => listInsights(projectId),
  });
  const tables = useQuery({
    queryKey: ["database-tables", projectId],
    queryFn: () => listProjectDatabaseTables(projectId),
  });
  const [mode, setMode] = useState<InsightMode>("list");
  const [search, setSearch] = useState("");
  const [selectedInsightId, setSelectedInsightId] = useState<string | null>(null);
  const selectedInsight = insights.data?.find(
    (insight) => insight.insight_id === selectedInsightId,
  );
  const [title, setTitle] = useState("New insight");
  const [description, setDescription] = useState("");
  const [store, setStore] = useState<Store>("analytics");
  const [table, setTable] = useState("");
  const [visualization, setVisualization] = useState("bar");
  const [xField, setXField] = useState("");
  const [yField, setYField] = useState("");
  const [aggregation, setAggregation] = useState("count");
  const [advancedSql, setAdvancedSql] = useState("");
  const availableTables = tables.data ?? [];
  const selectedTable = availableTables.find(
    (candidate) => candidate.store === store && candidate.name === table,
  );

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("new") === "1") {
      setSelectedInsightId(null);
      setTitle("New insight");
      setDescription("");
      setVisualization("bar");
      setAdvancedSql("");
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
    if (table || availableTables.length === 0) return;
    const preferred =
      availableTables.find((candidate) => candidate.name === "sample_metric_numeric") ??
      availableTables.find((candidate) => candidate.store === "analytics") ??
      availableTables[0];
    setStore(preferred.store);
    setTable(preferred.name);
    setXField(preferred.columns[0] ?? "");
    setYField(
      preferred.columns.find((column) => column === "value") ??
        preferred.columns[1] ??
        "",
    );
  }, [availableTables, table]);

  useEffect(() => {
    if (!selectedInsight) return;
    const config = selectedInsight.config;
    const query = isRecord(config.query) ? config.query : {};
    const source = parseSource(query.source);
    setTitle(selectedInsight.name);
    setDescription(selectedInsight.description ?? "");
    setVisualization(String(config.visualization ?? "bar"));
    setStore(source.store);
    setTable(source.table);
    setXField(firstString(query.x, query.dimensions, selectedTable?.columns[0]));
    setYField(firstString(query.y, undefined, selectedTable?.columns[1]));
    setAdvancedSql(typeof query.sql === "string" ? query.sql : "");
  }, [selectedInsight, selectedTable?.columns]);

  const config = useMemo(
    () =>
      buildConfig({
        title,
        description,
        store,
        table,
        visualization,
        xField,
        yField,
        aggregation,
        advancedSql,
      }),
    [
      advancedSql,
      aggregation,
      description,
      store,
      table,
      title,
      visualization,
      xField,
      yField,
    ],
  );
  const preview = useQuery({
    queryKey: ["insight-preview", projectId, selectedInsightId, config],
    queryFn: () =>
      executeInsight({
        insightId: selectedInsightId ?? undefined,
        projectId,
        config,
      }),
    enabled: mode === "detail" && Boolean(table || advancedSql.trim()),
    retry: false,
  });
  const save = useMutation({
    mutationFn: () =>
      selectedInsightId
        ? patchInsight(selectedInsightId, { name: title, description, config })
        : createInsight({ project_id: projectId, name: title, description, config }),
    onSuccess: (saved) => {
      setSelectedInsightId(saved.insight_id);
      setMode("detail");
      void queryClient.invalidateQueries({ queryKey: ["insights", projectId] });
      void queryClient.invalidateQueries({
        queryKey: ["insight-preview", projectId, saved.insight_id],
      });
    },
  });

  const openNewInsight = () => {
    setSelectedInsightId(null);
    setTitle("New insight");
    setDescription("");
    setVisualization("bar");
    setAdvancedSql("");
    setMode("detail");
  };

  if (mode === "list") {
    return (
      <Page title="Insights" subtitle="Create reusable charts, metrics, and tables.">
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
          <Button disabled={save.isPending} onClick={() => save.mutate()}>
            <Save className="h-4 w-4" /> Save
          </Button>
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
            <Field label="Visualization">
              <Select value={visualization} onValueChange={setVisualization}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {VISUALIZATIONS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {item.replace("_", " ")}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Store">
              <Select value={store} onValueChange={(value) => setStore(value as Store)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="analytics">DuckDB analytics</SelectItem>
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
                      <SelectItem key={`${item.store}:${item.name}`} value={item.name}>
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
            <Field label="Advanced SQL">
              <textarea
                className="min-h-[96px] w-full resize-y rounded-lg border border-[#cfd8e3] bg-white p-2 font-mono text-xs outline-none focus:ring-2 focus:ring-[#21a66a]"
                placeholder="SELECT ... (optional)"
                value={advancedSql}
                onChange={(event) => setAdvancedSql(event.target.value)}
              />
            </Field>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => void preview.refetch()}>
                <RefreshCw className="h-4 w-4" /> Refresh
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  setVisualization("table");
                  setStore("catalog");
                  setTable("samples");
                  setXField("sample_id");
                  setYField("sample_name");
                  setAggregation("count");
                  setAdvancedSql("");
                }}
              >
                <Table2 className="h-4 w-4" /> Clinical table
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="mt-0 min-h-0 overflow-hidden p-0">
          <CardContent className="flex h-full min-h-0 flex-col">
            <div className="flex items-center justify-between border-b border-[#dce3eb] px-4 py-3">
              <div>
                <h2 className="m-0 text-base font-semibold">{title}</h2>
                <p className="m-0 text-xs text-[#657082]">
                  {preview.data?.cached ? "Using cached result" : "Preview result"}
                </p>
              </div>
            </div>
            <div className="min-h-0 flex-1 p-4">
              {preview.error ? (
                <div className="rounded-md border border-[#fecaca] bg-[#fff1f2] p-3 text-sm text-[#b42318]">
                  {(preview.error as Error).message}
                </div>
              ) : (
                <InsightPreview result={preview.data} />
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/** Label-and-control wrapper used by the insight builder sidebar. */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
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

function buildConfig({
  title,
  description,
  store,
  table,
  visualization,
  xField,
  yField,
  aggregation,
  advancedSql,
}: {
  title: string;
  description: string;
  store: Store;
  table: string;
  visualization: string;
  xField: string;
  yField: string;
  aggregation: string;
  advancedSql: string;
}) {
  const query: Record<string, unknown> = {
    source: { store, table },
    dimensions: xField ? [xField] : [],
    measures: [
      { field: aggregation === "count" ? "*" : yField, aggregation, label: aggregation },
    ],
    limit: 1000,
  };
  if (advancedSql.trim()) query.sql = advancedSql.trim();
  if (visualization === "scatter" || visualization === "heatmap") {
    query.x = xField;
    query.y = yField;
  }
  if (visualization === "histogram") {
    const valueField = yField || xField;
    query.columns = valueField ? [valueField] : [];
    query.measures = [];
    query.dimensions = [];
    query.y = valueField;
  }
  if (visualization === "table") {
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
    display: {},
  };
}

function filterInsights(insights: SavedInsight[], search: string) {
  const normalized = search.trim().toLowerCase();
  if (!normalized) return insights;
  return insights.filter((insight) =>
    [insight.name, insight.description, insight.insight_id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalized)),
  );
}

function parseSource(value: unknown): { store: Store; table: string } {
  if (isRecord(value)) {
    return {
      store: value.store === "catalog" ? "catalog" : "analytics",
      table: typeof value.table === "string" ? value.table : "",
    };
  }
  if (typeof value === "string" && value.includes(".")) {
    const [store, table] = value.split(".", 2);
    return { store: store === "catalog" ? "catalog" : "analytics", table };
  }
  return { store: "analytics", table: typeof value === "string" ? value : "" };
}

function firstString(value: unknown, list: unknown, fallback: string | undefined) {
  if (typeof value === "string") return value;
  if (Array.isArray(list) && typeof list[0] === "string") return list[0];
  return fallback ?? "";
}
