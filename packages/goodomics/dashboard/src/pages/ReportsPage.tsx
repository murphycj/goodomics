import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ChevronDown,
  ExternalLink,
  LayoutGrid,
  MoreHorizontal,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import GridLayout, { type Layout } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import {
  createReport,
  deleteReport,
  executeReport,
  getProject,
  getReport,
  listInsights,
  listReports,
  listSampleGroups,
  patchReport,
  type InsightSummary,
  type ReportSummary,
  type SavedReport,
  type SampleGroup,
} from "../api";
import { InsightListTable } from "../components/reports/InsightListTable";
import { InsightPreview } from "../components/reports/InsightPreview";
import { ReportListTable } from "../components/reports/ReportListTable";
import {
  readReportItems,
  type ReportItem,
} from "../components/reports/reportUtils";
import {
  AsyncBlock,
  Button,
  Card,
  CardContent,
  ConfirmDialog,
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
  Label,
  Page,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui";
import { queryClient } from "../lib/queryClient";
import { useAuth } from "../components/auth/AuthProvider";
import { cn } from "../lib/utils";
import { isRecord, stringValue } from "../lib/valueUtils";

type ReportMode = "list" | "detail";
type ReportTarget =
  | { mode: "list" }
  | { mode: "new" }
  | { mode: "view"; reportRef: string }
  | { mode: "edit"; reportRef: string };

/** Report index and grid-layout builder for composing saved insights. */
export function ReportsPage({
  projectId,
  target = { mode: "list" },
}: {
  projectId: string;
  target?: ReportTarget;
}) {
  const { can } = useAuth();
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
  const sampleGroups = useQuery({
    queryKey: ["sample-groups", projectId, "sample_group"],
    queryFn: () => listSampleGroups(projectId, "sample_group"),
  });
  const mode: ReportMode = target.mode === "list" ? "list" : "detail";
  const isNewReport = target.mode === "new";
  const canSaveReport = isNewReport ? true : can("report.edit", projectId);
  const isEditingDetails = target.mode === "new" || target.mode === "edit";
  const [search, setSearch] = useState("");
  const selectedReportSummary = reports.data?.find(
    (report) =>
      target.mode !== "list" &&
      target.mode !== "new" &&
      (report.report_id === target.reportRef ||
        report.url_slug === target.reportRef),
  );
  const selectedReportRef =
    target.mode === "view" || target.mode === "edit"
      ? target.reportRef
      : selectedReportSummary?.report_id;
  const reportDetail = useQuery({
    queryKey: ["report", selectedReportRef],
    queryFn: () => getReport(selectedReportRef!),
    enabled: Boolean(selectedReportRef),
  });
  const selectedReport = reportDetail.data;
  const selectedReportId =
    selectedReportSummary?.report_id ?? selectedReport?.report_id ?? null;
  const [editMode, setEditMode] = useState(false);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [addSearch, setAddSearch] = useState("");
  const [name, setName] = useState("Project report");
  const [description, setDescription] = useState("");
  const [sampleGroupId, setSampleGroupId] = useState("");
  const [sampleIdsInput, setSampleIdsInput] = useState("");
  const [items, setItems] = useState<ReportItem[]>([]);

  useEffect(() => {
    if (isNewReport) {
      setName("Project report");
      setDescription("");
      setSampleGroupId("");
      setSampleIdsInput("");
      setItems([]);
      setEditMode(true);
      return;
    }
    if (!selectedReport) return;
    setName(selectedReport.name);
    setDescription(selectedReport.description ?? "");
    const selection = readReportSampleFilter(selectedReport.filters);
    setSampleGroupId(selection.sampleGroupId);
    setSampleIdsInput(selection.sampleIds.join(", "));
    setItems(readReportItems(selectedReport));
    setEditMode(target.mode === "edit");
  }, [isNewReport, selectedReport, target.mode]);

  const result = useQuery({
    queryKey: ["report-result", projectId, selectedReportId],
    queryFn: () => executeReport({ reportId: selectedReportId!, projectId }),
    enabled: mode === "detail" && Boolean(selectedReportId),
    retry: false,
  });
  const saveReport = useMutation({
    mutationFn: async (continueEditing: boolean) => {
      const config = {
        version: 1,
        layout: { columns: 12 },
        items,
        filters: buildReportFilters({ sampleIdsInput, sampleGroupId }),
        refresh_policy: { mode: "manual" },
      };
      if (selectedReportId) {
        return patchReport(selectedReportId, { ...config, name, description });
      }
      return createReport({
        ...config,
        project_id: projectId,
        name,
        description,
      });
    },
    onSuccess: (saved, continueEditing) => {
      void queryClient.invalidateQueries({ queryKey: ["reports", projectId] });
      void queryClient.invalidateQueries({
        queryKey: ["report-result", projectId, saved.report_id],
      });
      window.location.href = continueEditing
        ? `/project/${projectId}/reports/${encodeURIComponent(saved.url_slug)}/edit`
        : `/project/${projectId}/reports`;
    },
  });
  const removeReport = useMutation({
    mutationFn: (reportId: string) => deleteReport(reportId),
    onSuccess: () => {
      setDeleteDialogOpen(false);
      void queryClient.invalidateQueries({ queryKey: ["reports", projectId] });
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      window.location.href = `/project/${projectId}/reports`;
    },
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
  const insightResults = Array.isArray(result.data?.insights)
    ? result.data.insights
    : [];
  const insightById = new Map(
    insightResults
      .filter(isRecord)
      .map((item) => [String(item.insight_id ?? ""), item] as const),
  );
  const selectedInsightIds = useMemo(
    () => new Set(items.map((item) => item.insight_id)),
    [items],
  );

  if (mode === "list") {
    return (
      <Page
        title="Reports"
        subtitle="Create and manage reusable project reports."
      >
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
          <Button
            onClick={() => {
              window.location.href = `/project/${projectId}/reports/new`;
            }}
          >
            <Plus className="h-4 w-4" /> New report
          </Button>
        </div>
        <AsyncBlock query={reports} empty="No saved reports yet.">
          {(data) => (
            <ReportListTable
              defaultReportId={project.data?.default_report_id ?? null}
              reports={filterReports(data, search)}
              onOpen={(report) => {
                window.location.href = `/project/${projectId}/reports/${encodeURIComponent(
                  report.url_slug,
                )}`;
              }}
            />
          )}
        </AsyncBlock>
      </Page>
    );
  }

  return (
    <div className="flex h-[calc(100vh-48px)] min-h-0 flex-col gap-4">
      <ConfirmDialog
        confirmLabel="Delete report"
        description={`Delete “${name}”? This action cannot be undone.`}
        error={removeReport.error?.message}
        isPending={removeReport.isPending}
        onConfirm={() => {
          if (selectedReportId) removeReport.mutate(selectedReportId);
        }}
        onOpenChange={(open) => {
          setDeleteDialogOpen(open);
          if (!open) removeReport.reset();
        }}
        open={deleteDialogOpen}
        title="Delete report"
        tone="destructive"
      />
      {isEditingDetails ? (
        <ReportBuilderHeader
          description={description}
          isSaving={saveReport.isPending}
          canSave={canSaveReport}
          name={name}
          onBack={() => {
            window.location.href = selectedReport?.url_slug
              ? `/project/${projectId}/reports/${encodeURIComponent(
                  selectedReport.url_slug,
                )}`
              : `/project/${projectId}/reports`;
          }}
          onDescriptionChange={setDescription}
          onSave={() => saveReport.mutate(false)}
          onSaveContinue={() => saveReport.mutate(true)}
          onNameChange={setName}
        />
      ) : (
        <ReportReadHeader
          description={description}
          isDeleting={removeReport.isPending}
          isLayoutEditing={editMode}
          projectName={project.data?.name ?? projectId}
          report={selectedReport}
          name={name}
          onBack={() => {
            window.location.href = `/project/${projectId}/reports`;
          }}
          onChangeLayout={() => setEditMode(true)}
          onDelete={() => {
            removeReport.reset();
            setDeleteDialogOpen(true);
          }}
          onEdit={() => {
            if (!selectedReport?.url_slug) return;
            window.location.href = `/project/${projectId}/reports/${encodeURIComponent(
              selectedReport.url_slug,
            )}/edit`;
          }}
          onRefresh={() => void result.refetch()}
          onSaveLayout={() => saveReport.mutate(false)}
        />
      )}

      {saveReport.error instanceof Error ? (
        <div
          className="rounded-md border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-sm text-[#b42318]"
          role="alert"
        >
          {saveReport.error.message}
        </div>
      ) : null}

      {isEditingDetails || editMode ? (
        <section className="shrink-0 border-b border-[#dce3eb] pb-4">
          <div className="flex flex-wrap items-center gap-3">
            <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
              <DialogTrigger asChild>
                <Button disabled={!editMode}>
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
                      <div className="text-sm font-semibold">
                        Create a new insight
                      </div>
                      <div className="mt-1 text-xs text-[#657082]">
                        Build a chart, metric, or table, then add it to this
                        report.
                      </div>
                    </div>
                    <Button
                      variant="outline"
                      onClick={() => {
                        window.location.href = `/project/${projectId}/insights/new`;
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
                                  (item) =>
                                    item.insight_id === insight.insight_id,
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
            <Button
              variant="secondary"
              onClick={() => setEditMode((value) => !value)}
            >
              <LayoutGrid className="h-4 w-4" />{" "}
              {editMode ? "View" : "Edit layout"}
            </Button>
            {selectedReportId && isEditingDetails ? (
              <Button variant="outline" onClick={() => void result.refetch()}>
                <RefreshCw className="h-4 w-4" /> Refresh
              </Button>
            ) : null}
          </div>
          {isEditingDetails ? (
            <ReportSampleFilterControls
              sampleIdsInput={sampleIdsInput}
              sampleGroupId={sampleGroupId}
              sampleGroups={sampleGroups.data ?? []}
              onSampleIdsInputChange={setSampleIdsInput}
              onSampleGroupIdChange={setSampleGroupId}
            />
          ) : null}
        </section>
      ) : null}

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
                        ? {
                            ...item,
                            x: next.x,
                            y: next.y,
                            w: next.w,
                            h: next.h,
                          }
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
                        insightRef={
                          insights.data?.find(
                            (insight) => insight.insight_id === item.insight_id,
                          )?.url_slug ?? item.insight_id
                        }
                        projectId={projectId}
                        onRefresh={() => void result.refetch()}
                        onRemove={() =>
                          setItems((current) =>
                            current.filter(
                              (candidate) =>
                                candidate.insight_id !== item.insight_id,
                            ),
                          )
                        }
                      />
                    </div>
                    <div className="h-[calc(100%-42px)] min-h-0 p-3">
                      <InsightPreview
                        result={insightById.get(item.insight_id)}
                      />
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

function ReportBuilderHeader({
  name,
  description,
  isSaving,
  canSave,
  onBack,
  onDescriptionChange,
  onSave,
  onSaveContinue,
  onNameChange,
}: {
  name: string;
  description: string;
  isSaving: boolean;
  canSave: boolean;
  onBack: () => void;
  onDescriptionChange: (value: string) => void;
  onSave: () => void;
  onSaveContinue: () => void;
  onNameChange: (value: string) => void;
}) {
  const hasDescription = Boolean(description.trim());
  const [showDescription, setShowDescription] = useState(hasDescription);

  useEffect(() => {
    if (description.trim()) setShowDescription(true);
  }, [description]);

  return (
    <section className="shrink-0 border-b border-[#dce3eb] pb-4">
      <div className="flex items-center gap-3">
        <Button size="icon" variant="ghost" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <LayoutGrid className="h-5 w-5 text-[#16784a]" />
        <Input
          className="h-10 flex-1 text-lg font-semibold"
          value={name}
          onChange={(event) => onNameChange(event.target.value)}
        />
        <Button
          className="bg-[#eef2f6] text-[#526071] hover:bg-[#e3e9f0] hover:text-[#1f2937]"
          type="button"
          variant="ghost"
          onClick={() => setShowDescription(true)}
        >
          {hasDescription ? (
            <>
              <Pencil className="h-4 w-4" /> Description
            </>
          ) : (
            <>
              <Plus className="h-4 w-4" /> Description
            </>
          )}
        </Button>
        {canSave && (
          <div className="flex overflow-hidden rounded-lg shadow-sm">
            <Button
              className="rounded-r-none"
              disabled={isSaving}
              onClick={onSave}
            >
              <Save className="h-4 w-4" /> Save
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  aria-label="Save options"
                  className="rounded-l-none border-l border-[#16864f] px-2.5"
                  disabled={isSaving}
                >
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-[240px]">
                <DropdownMenuItem onClick={onSaveContinue}>
                  <Save className="h-4 w-4" /> Save & continue editing
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}
      </div>
      {showDescription ? (
        <div className="mt-3 flex items-start gap-2">
          <textarea
            className="h-10 min-h-10 flex-1 resize-y rounded-md border border-[#d6dee8] bg-white px-3 py-2 text-sm text-[#1f2937] outline-none transition-colors placeholder:text-[#9ca3af] focus:border-[#16784a] focus:ring-2 focus:ring-[#16784a]/15"
            placeholder="Enter description (optional)"
            rows={1}
            value={description}
            onChange={(event) => onDescriptionChange(event.target.value)}
          />
          <Button
            aria-label="Hide description"
            className="mt-1 shrink-0 text-[#657082] hover:text-[#1f2937]"
            size="icon"
            type="button"
            variant="ghost"
            onClick={() => setShowDescription(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function ReportReadHeader({
  description,
  isDeleting,
  isLayoutEditing,
  projectName,
  report,
  name,
  onBack,
  onChangeLayout,
  onDelete,
  onEdit,
  onRefresh,
  onSaveLayout,
}: {
  description: string;
  isDeleting: boolean;
  isLayoutEditing: boolean;
  projectName: string;
  report: SavedReport | undefined;
  name: string;
  onBack: () => void;
  onChangeLayout: () => void;
  onDelete: () => void;
  onEdit: () => void;
  onRefresh: () => void;
  onSaveLayout: () => void;
}) {
  return (
    <section className="shrink-0 border-b border-[#dce3eb] pb-4">
      <div className="flex items-start gap-3">
        <Button size="icon" variant="ghost" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <LayoutGrid className="mt-2 h-5 w-5 shrink-0 text-[#16784a]" />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-xl font-semibold text-[#1d2430]">
            {name}
          </h1>
          <div className="mt-1 text-xs font-medium uppercase text-[#657082]">
            {projectName}
          </div>
          {description.trim() ? (
            <p className="mt-2 max-w-[860px] text-sm text-[#526071]">
              {description}
            </p>
          ) : null}
        </div>
        {isLayoutEditing ? (
          <Button onClick={onSaveLayout}>
            <Save className="h-4 w-4" /> Save layout
          </Button>
        ) : null}
        <Button disabled={!report} variant="outline" onClick={onRefresh}>
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              aria-label="Report actions"
              disabled={!report || isDeleting}
              size="icon"
              variant="ghost"
            >
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>Report</DropdownMenuLabel>
            <DropdownMenuItem onClick={onEdit}>
              <Pencil className="h-4 w-4" /> Edit details
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onChangeLayout}>
              <LayoutGrid className="h-4 w-4" /> Change layout
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-[#b42318]" onClick={onDelete}>
              <Trash2 className="h-4 w-4" /> Delete report
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </section>
  );
}

/** Per-insight action menu shown in report cards. */
function InsightCardMenu({
  insightRef,
  onRefresh,
  onRemove,
  projectId,
}: {
  insightRef: string;
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
            window.location.href = `/project/${projectId}/insights/${encodeURIComponent(
              insightRef,
            )}/edit`;
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

function filterReports(reports: ReportSummary[], search: string) {
  const normalized = search.trim().toLowerCase();
  if (!normalized) return reports;
  return reports.filter((report) =>
    [report.name, report.description, report.report_id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalized)),
  );
}

function ReportSampleFilterControls({
  sampleIdsInput,
  sampleGroupId,
  sampleGroups,
  onSampleIdsInputChange,
  onSampleGroupIdChange,
}: {
  sampleIdsInput: string;
  sampleGroupId: string;
  sampleGroups: SampleGroup[];
  onSampleIdsInputChange: (value: string) => void;
  onSampleGroupIdChange: (value: string) => void;
}) {
  return (
    <div className="mt-3 grid gap-3 md:grid-cols-2">
      <div className="space-y-1.5">
        <Label>Sample IDs</Label>
        <Input
          placeholder="S1, S2"
          value={sampleIdsInput}
          onChange={(event) => onSampleIdsInputChange(event.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <Label>Sample group</Label>
          {sampleGroupId ? (
            <Button
              className="h-auto px-1 py-0 text-xs"
              type="button"
              variant="ghost"
              onClick={() => onSampleGroupIdChange("")}
            >
              Clear
            </Button>
          ) : null}
        </div>
        <Select value={sampleGroupId} onValueChange={onSampleGroupIdChange}>
          <SelectTrigger>
            <SelectValue placeholder="All samples" />
          </SelectTrigger>
          <SelectContent>
            {sampleGroups.map((sampleGroup) => (
              <SelectItem
                key={sampleGroup.sample_group_id}
                value={sampleGroup.sample_group_id}
              >
                {sampleGroup.name} ({sampleGroup.member_count})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}

// builds the report filters from the sample IDs and sample group ID
function buildReportFilters({
  sampleIdsInput,
  sampleGroupId,
}: {
  sampleIdsInput: string;
  sampleGroupId: string;
}) {
  // parse the sample IDs from the text input, trimming whitespace and filtering out empty values
  const sampleIds = sampleIdsInput
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);

  const value = [
    ...sampleIds.map((id) => ({ kind: "sample", id })),
    ...(sampleGroupId ? [{ kind: "sample_group", id: sampleGroupId }] : []),
  ];
  return value.length ? [{ field: "sample", operator: "in", value }] : [];
}

// reads the report filters and returns the sample IDs and sample group ID
function readReportSampleFilter(value: unknown) {
  const references = Array.isArray(value)
    ? value
        .filter(isRecord)
        .filter((filter) => filter.field === "sample")
        .flatMap((filter) =>
          Array.isArray(filter.value) ? filter.value.filter(isRecord) : [],
        )
    : [];

  // return the sample IDs and sample group ID, filtering out any non-string values
  return {
    sampleIds: references
      .filter((reference) => reference.kind === "sample")
      .map((reference) => stringValue(reference.id))
      .filter(Boolean),
    sampleGroupId:
      references
        .filter((reference) => reference.kind === "sample_group")
        .map((reference) => stringValue(reference.id))
        .find(Boolean) ?? "",
  };
}

function filterInsights(insights: InsightSummary[], search: string) {
  const normalized = search.trim().toLowerCase();
  if (!normalized) return insights;
  return insights.filter((insight) =>
    [insight.name, insight.description, insight.insight_id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalized)),
  );
}

function insightTitle(insights: InsightSummary[], insightId: string) {
  return (
    insights.find((insight) => insight.insight_id === insightId)?.name ??
    insightId
  );
}
