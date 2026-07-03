import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ExternalLink,
  LayoutGrid,
  MoreHorizontal,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings2,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import GridLayout, { type Layout } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import {
  createReport,
  executeReport,
  getProject,
  listInsights,
  listReports,
  patchProject,
  patchReport,
  type SavedInsight,
  type SavedReport,
} from "../api";
import { InsightListTable } from "../components/reports/InsightListTable";
import { InsightPreview } from "../components/reports/InsightPreview";
import { ReportListTable } from "../components/reports/ReportListTable";
import {
  isRecord,
  readReportItems,
  type ReportItem,
} from "../components/reports/reportUtils";
import {
  AsyncBlock,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogContent,
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
  Page,
} from "../components/ui";
import { queryClient } from "../lib/queryClient";
import { cn } from "../lib/utils";

type ReportMode = "list" | "detail";

/** Report index and grid-layout builder for composing saved insights. */
export function ReportsPage({
  initialReportId,
  projectId,
}: {
  initialReportId?: string | null;
  projectId: string;
}) {
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
  });
  const reports = useQuery({
    queryKey: ["reports", projectId],
    queryFn: () => listReports(projectId),
  });
  const insights = useQuery({
    queryKey: ["insights", projectId],
    queryFn: () => listInsights(projectId),
  });
  const [mode, setMode] = useState<ReportMode>(initialReportId ? "detail" : "list");
  const [search, setSearch] = useState("");
  const [selectedReportId, setSelectedReportId] = useState<string | null>(
    initialReportId ?? null,
  );
  const selectedReport = reports.data?.find(
    (report) => report.report_id === selectedReportId,
  );
  const [editMode, setEditMode] = useState(false);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [addSearch, setAddSearch] = useState("");
  const [name, setName] = useState("Project report");
  const [description, setDescription] = useState("");
  const [items, setItems] = useState<ReportItem[]>([]);

  useEffect(() => {
    if (!initialReportId) return;
    setSelectedReportId(initialReportId);
    setMode("detail");
  }, [initialReportId]);

  useEffect(() => {
    if (!selectedReport) return;
    setName(selectedReport.name);
    setDescription(selectedReport.description ?? "");
    setItems(readReportItems(selectedReport.config));
  }, [selectedReport]);

  const result = useQuery({
    queryKey: ["report-result", projectId, selectedReportId],
    queryFn: () => executeReport({ reportId: selectedReportId!, projectId }),
    enabled: mode === "detail" && Boolean(selectedReportId),
    retry: false,
  });
  const saveReport = useMutation({
    mutationFn: async () => {
      const config = {
        version: 1,
        title: name,
        description,
        layout: { columns: 12 },
        items,
        filters: [],
        refresh_policy: { mode: "manual" },
      };
      if (selectedReportId) {
        return patchReport(selectedReportId, { name, description, config });
      }
      return createReport({ project_id: projectId, name, description, config });
    },
    onSuccess: (saved) => {
      setSelectedReportId(saved.report_id);
      setMode("detail");
      void queryClient.invalidateQueries({ queryKey: ["reports", projectId] });
      void queryClient.invalidateQueries({
        queryKey: ["report-result", projectId, saved.report_id],
      });
    },
  });
  const defaultReport = useMutation({
    mutationFn: (reportId: string) =>
      patchProject(projectId, { default_report_id: reportId }),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
  });
  const layout = useMemo<Layout>(
    () =>
      items.map((item) => ({
        i: item.insight_id,
        x: item.x,
        y: item.y,
        w: item.w,
        h: item.h,
        minW: 3,
        minH: 3,
        static: !editMode,
        isDraggable: editMode,
        isResizable: editMode,
      })),
    [editMode, items],
  );
  const insightResults = Array.isArray(result.data?.insights) ? result.data.insights : [];
  const insightById = new Map(
    insightResults
      .filter(isRecord)
      .map((item) => [String(item.insight_id ?? ""), item] as const),
  );
  const selectedInsightIds = useMemo(
    () => new Set(items.map((item) => item.insight_id)),
    [items],
  );

  const openNewReport = () => {
    setSelectedReportId(null);
    setName("Project report");
    setDescription("");
    setItems([]);
    setEditMode(true);
    setMode("detail");
  };

  if (mode === "list") {
    return (
      <Page title="Reports" subtitle="Create and manage reusable project reports.">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="relative w-full max-w-[320px]">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#758195]" />
            <Input
              className="pl-9"
              placeholder="Search reports..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <Button onClick={openNewReport}>
            <Plus className="h-4 w-4" /> New report
          </Button>
        </div>
        <AsyncBlock query={reports} empty="No saved reports yet.">
          {(data) => (
            <ReportListTable
              defaultReportId={project.data?.default_report_id ?? null}
              reports={filterReports(data, search)}
              onOpen={(report) => {
                setSelectedReportId(report.report_id);
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
          <LayoutGrid className="h-5 w-5 text-[#16784a]" />
          <Input
            className="h-10 flex-1 text-lg font-semibold"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Button variant="outline" onClick={() => void result.refetch()}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
          <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4" /> Add
              </Button>
            </DialogTrigger>
            <DialogContent className="max-h-[86vh] max-w-[980px] gap-0 overflow-hidden p-0">
              <DialogHeader className="border-b border-[#dce3eb] px-5 py-4">
                <DialogTitle>Add insight to report</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 overflow-y-auto p-5">
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#dce3eb] bg-[#f7f8fa] p-4">
                  <div>
                    <div className="text-sm font-semibold">Create a new insight</div>
                    <div className="mt-1 text-xs text-[#657082]">
                      Build a chart, metric, or table, then add it to this report.
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    onClick={() => {
                      window.location.href = `/project/${projectId}/insights?new=1`;
                    }}
                  >
                    <ExternalLink className="h-4 w-4" /> New insight
                  </Button>
                </div>
                <div className="relative max-w-[320px]">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#758195]" />
                  <Input
                    className="pl-9"
                    placeholder="Search insights..."
                    value={addSearch}
                    onChange={(event) => setAddSearch(event.target.value)}
                  />
                </div>
                <AsyncBlock query={insights} empty="No saved insights yet.">
                  {(data) => (
                    <div className="max-h-[52vh] overflow-y-auto rounded-lg border border-[#dce3eb]">
                      <InsightListTable
                        insights={filterInsights(data, addSearch)}
                        selectedInsightIds={selectedInsightIds}
                        onAdd={(insight) =>
                          setItems((current) => {
                            if (
                              current.some(
                                (item) => item.insight_id === insight.insight_id,
                              )
                            ) {
                              return current;
                            }
                            return [
                              ...current,
                              {
                                insight_id: insight.insight_id,
                                x: 0,
                                y: Infinity,
                                w: 6,
                                h: 5,
                              },
                            ];
                          })
                        }
                      />
                    </div>
                  )}
                </AsyncBlock>
              </div>
            </DialogContent>
          </Dialog>
          <Button variant="secondary" onClick={() => setEditMode((value) => !value)}>
            <LayoutGrid className="h-4 w-4" /> {editMode ? "View" : "Edit layout"}
          </Button>
          <Button
            disabled={!selectedReportId}
            variant="outline"
            onClick={() => selectedReportId && defaultReport.mutate(selectedReportId)}
          >
            <Settings2 className="h-4 w-4" /> Default
          </Button>
          <Button disabled={saveReport.isPending} onClick={() => saveReport.mutate()}>
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

      <div className="min-h-0 flex-1">
        <Card className="mt-0 min-h-0 overflow-auto p-0">
          <CardContent className="min-h-full bg-[#f7f8fa] p-4">
            {result.error ? (
              <div className="rounded-md border border-[#fecaca] bg-[#fff1f2] p-3 text-sm text-[#b42318]">
                {(result.error as Error).message}
              </div>
            ) : items.length === 0 ? (
              <div className="grid min-h-[360px] place-items-center rounded-lg border border-dashed border-[#cfd8e3] bg-white text-sm text-[#657082]">
                Add saved insights to build this report.
              </div>
            ) : (
              <GridLayout
                className={cn("layout", editMode && "report-grid-editing")}
                dragConfig={{
                  enabled: editMode,
                  handle: ".report-card-drag-handle",
                  threshold: 3,
                }}
                gridConfig={{
                  cols: 12,
                  rowHeight: 64,
                  margin: [14, 14],
                  containerPadding: [0, 0],
                }}
                layout={layout}
                onLayoutChange={(nextLayout) => {
                  if (!editMode) return;
                  setItems((current) =>
                    current.map((item) => {
                      const next = nextLayout.find(
                        (layoutItem) => layoutItem.i === item.insight_id,
                      );
                      return next
                        ? { ...item, x: next.x, y: next.y, w: next.w, h: next.h }
                        : item;
                    }),
                  );
                }}
                resizeConfig={{ enabled: editMode, handles: ["se", "e", "s"] }}
                width={1120}
              >
                {items.map((item) => (
                  <div className="report-card" key={item.insight_id}>
                    <div className="report-card-header flex items-center justify-between gap-2 border-b border-[#dce3eb] px-3 py-2">
                      <span className="report-card-drag-handle min-w-0 flex-1 truncate text-sm font-semibold">
                        {insightTitle(insights.data ?? [], item.insight_id)}
                      </span>
                      <InsightCardMenu
                        insightId={item.insight_id}
                        projectId={projectId}
                        onRefresh={() => void result.refetch()}
                        onRemove={() =>
                          setItems((current) =>
                            current.filter(
                              (candidate) => candidate.insight_id !== item.insight_id,
                            ),
                          )
                        }
                      />
                    </div>
                    <div className="h-[calc(100%-42px)] min-h-0 p-3">
                      <InsightPreview result={insightById.get(item.insight_id)} />
                    </div>
                  </div>
                ))}
              </GridLayout>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/** Per-insight action menu shown in report cards. */
function InsightCardMenu({
  insightId,
  onRefresh,
  onRemove,
  projectId,
}: {
  insightId: string;
  onRefresh: () => void;
  onRemove: () => void;
  projectId: string;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          aria-label="Insight actions"
          className="h-8 w-8 shrink-0"
          size="icon"
          variant="ghost"
        >
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Insight</DropdownMenuLabel>
        <DropdownMenuItem
          onClick={() => {
            window.location.href = `/project/${projectId}/insights?insight=${encodeURIComponent(
              insightId,
            )}`;
          }}
        >
          <Pencil className="h-4 w-4" /> Edit insight
        </DropdownMenuItem>
        <DropdownMenuItem onClick={onRefresh}>
          <RefreshCw className="h-4 w-4" /> Refresh data
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem className="text-[#b42318]" onClick={onRemove}>
          <Trash2 className="h-4 w-4" /> Remove from report
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function filterReports(reports: SavedReport[], search: string) {
  const normalized = search.trim().toLowerCase();
  if (!normalized) return reports;
  return reports.filter((report) =>
    [report.name, report.description, report.report_id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalized)),
  );
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

function insightTitle(insights: SavedInsight[], insightId: string) {
  return insights.find((insight) => insight.insight_id === insightId)?.name ?? insightId;
}
