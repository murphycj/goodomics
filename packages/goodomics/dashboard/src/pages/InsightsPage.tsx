import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ChevronDown,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Settings2,
  Trash2,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  bulkDeleteInsights,
  createInsight,
  deleteInsight,
  duplicateInsight,
  executeInsight,
  getInsight,
  listCatalogDatasets,
  listInsights,
  listReports,
  patchInsight,
  renameInsight,
  searchCatalogFields,
  validateInsightConfig,
  type InsightSummary,
} from "../api";
import { useAuth } from "../components/auth/AuthProvider";
import { InsightBuilderHeader } from "../components/insights/InsightBuilderHeader";
import {
  InsightFieldCard,
  selectedCatalogField,
} from "../components/insights/InsightFieldCard";
import {
  catalogSelection,
  InsightFieldPicker,
  type CatalogField,
} from "../components/insights/InsightFieldPicker";
import { InsightPreviewPanel } from "../components/insights/InsightPreviewPanel";
import { InsightViewThumbnail } from "../components/insights/InsightViewThumbnail";
import { InsightListTable } from "../components/reports/InsightListTable";
import { SavedItemRenameDialog } from "../components/reports/SavedItemRenameDialog";
import {
  AnalysisTypeDialog,
  AnalysisTypePicker,
  analysisType,
  ToolbarField,
  ViewPicker,
} from "../components/insights/InsightVisualSelectors";
import {
  AsyncBlock,
  Button,
  Card,
  CardContent,
  ConfirmDialog,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Input,
  Page,
} from "../components/ui";
import {
  createView,
  emptyInsightDraft,
  switchQueryFamily,
  titleCase,
} from "../lib/insightBuilder";
import {
  insightDefinitionSchema,
  type FieldSelection,
  type InsightDraft,
  type QueryKind,
  type QueryNode,
  type ViewKind,
} from "../lib/insightSchemas";
import { queryClient } from "../lib/queryClient";

type InsightTarget =
  | { mode: "list" }
  | { mode: "new"; queryKind?: QueryKind }
  | { mode: "view"; insightRef: string }
  | { mode: "edit"; insightRef: string };

type CatalogDataset = {
  data_contract_id: string;
  name: string;
};

type Grain = "sample" | "subject" | "run" | "feature" | "variant" | "file" | "row";
const GRAINS: Grain[] = ["sample", "subject", "run", "feature", "variant", "file", "row"];

/** Catalog-driven v2 insight index and visual family-specific builder. */
export function InsightsPage({
  projectId,
  target = { mode: "list" },
}: {
  projectId: string;
  target?: InsightTarget;
}) {
  if (target.mode === "list") return <InsightIndex projectId={projectId} />;
  if (target.mode === "view") {
    return <InsightReadView insightRef={target.insightRef} projectId={projectId} />;
  }
  return <InsightBuilder projectId={projectId} target={target} />;
}

function InsightIndex({ projectId }: { projectId: string }) {
  const { can } = useAuth();
  const [search, setSearch] = useState("");
  const [selectedInsightIds, setSelectedInsightIds] = useState<Set<string>>(new Set());
  const [renameTarget, setRenameTarget] = useState<InsightSummary | null>(null);
  const [deleteTargets, setDeleteTargets] = useState<InsightSummary[]>([]);
  const [bulkInsightDelete, setBulkInsightDelete] = useState(false);
  const [newInsightOpen, setNewInsightOpen] = useState(false);
  const insights = useQuery({
    queryKey: ["insights", projectId],
    queryFn: () => listInsights(projectId),
  });
  const reports = useQuery({
    queryKey: ["reports", projectId],
    queryFn: () => listReports(projectId),
  });
  const rows = useMemo(() => filterInsights(insights.data ?? [], search), [insights.data, search]);
  const selectedRows = useMemo(
    () => (insights.data ?? []).filter((insight) => selectedInsightIds.has(insight.insight_id)),
    [insights.data, selectedInsightIds],
  );
  const reportCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const report of reports.data ?? []) {
      for (const insightId of new Set(report.insight_ids)) {
        counts.set(insightId, (counts.get(insightId) ?? 0) + 1);
      }
    }
    return counts;
  }, [reports.data]);
  const renameListInsight = useMutation({
    mutationFn: ({ insightId, nextName }: { insightId: string; nextName: string }) =>
      renameInsight(insightId, nextName),
    onSuccess: () => {
      setRenameTarget(null);
      void queryClient.invalidateQueries({ queryKey: ["insights", projectId] });
    },
  });
  const duplicateListInsight = useMutation({
    mutationFn: (insightRef: string) => duplicateInsight(projectId, insightRef),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["insights", projectId] }),
  });
  const removeListInsights = useMutation({
    mutationFn: async ({ ids, bulk }: { ids: string[]; bulk: boolean }) => {
      if (bulk) await bulkDeleteInsights(projectId, ids);
      else await deleteInsight(ids[0]!);
    },
    onSuccess: (_result, variables) => {
      setDeleteTargets([]);
      setBulkInsightDelete(false);
      setSelectedInsightIds((current) => {
        const next = new Set(current);
        for (const id of variables.ids) next.delete(id);
        return next;
      });
      void queryClient.invalidateQueries({ queryKey: ["insights", projectId] });
    },
  });
  const canEditInsights = can("insight.edit", projectId);
  const canDeleteInsights = can("insight.delete", projectId);

  return (
    <Page title="Insights" subtitle="Create reusable values, tables, and charts.">
      <AnalysisTypeDialog
        open={newInsightOpen}
        onOpenChange={setNewInsightOpen}
        onSelect={(kind) => {
          window.location.href = `/project/${projectId}/insights/new?analysis=${encodeURIComponent(kind)}`;
        }}
      />
      <SavedItemRenameDialog
        error={renameListInsight.error?.message}
        isPending={renameListInsight.isPending}
        itemName={renameTarget?.name ?? ""}
        noun="insight"
        open={Boolean(renameTarget)}
        onOpenChange={(open) => {
          if (!open) {
            setRenameTarget(null);
            renameListInsight.reset();
          }
        }}
        onRename={(nextName) => {
          if (renameTarget) renameListInsight.mutate({ insightId: renameTarget.insight_id, nextName });
        }}
      />
      <ConfirmDialog
        confirmLabel={deleteTargets.length > 1 ? "Delete insights" : "Delete insight"}
        description={bulkInsightDelete
          ? `Delete ${deleteTargets.length} selected ${deleteTargets.length === 1 ? "insight" : "insights"}? This action cannot be undone.`
          : `Delete “${deleteTargets[0]?.name ?? "this insight"}”? This action cannot be undone.`}
        error={removeListInsights.error?.message}
        isPending={removeListInsights.isPending}
        open={deleteTargets.length > 0}
        title={bulkInsightDelete ? "Delete selected insights" : "Delete insight"}
        tone="destructive"
        onOpenChange={(open) => {
          if (!open) {
            setDeleteTargets([]);
            setBulkInsightDelete(false);
            removeListInsights.reset();
          }
        }}
        onConfirm={() => {
          const ids = deleteTargets.map((insight) => insight.insight_id);
          if (ids.length) removeListInsights.mutate({ ids, bulk: bulkInsightDelete });
        }}
      />
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
        <div className="ml-auto flex items-center gap-2">
          {selectedRows.length ? (
            <>
              <span className="text-sm text-[#657082]">{selectedRows.length} selected</span>
              <Button
                className="border-[#efb4ae] text-[#b42318] hover:border-[#dc8f87] hover:bg-[#fff1f2]"
                variant="outline"
                onClick={() => {
                  setBulkInsightDelete(true);
                  setDeleteTargets(selectedRows);
                }}
              >
                <Trash2 className="h-4 w-4" /> Delete selected
              </Button>
            </>
          ) : null}
          <Button onClick={() => setNewInsightOpen(true)}>
            <Plus className="h-4 w-4" /> New insight
          </Button>
        </div>
      </div>
      <AsyncBlock query={insights} empty="No saved insights yet.">
        {() => (
          <InsightListTable
            actions={{
              canDelete: canDeleteInsights,
              canDuplicate: can("insight.create", projectId),
              canEdit: canEditInsights,
              onDelete: (insight) => {
                setBulkInsightDelete(false);
                setDeleteTargets([insight]);
              },
              onDuplicate: (insight) => duplicateListInsight.mutate(insight.insight_id),
              onEdit: (insight) => {
                window.location.href = `/project/${projectId}/insights/${encodeURIComponent(insight.url_slug)}/edit`;
              },
              onRename: setRenameTarget,
              onView: (insight) => {
                window.location.href = `/project/${projectId}/insights/${encodeURIComponent(insight.url_slug)}`;
              },
            }}
            insights={rows}
            reportCounts={reportCounts}
            onOpen={(insight) => {
              window.location.href = `/project/${projectId}/insights/${encodeURIComponent(insight.url_slug)}`;
            }}
            selection={{
              disabled: !canDeleteInsights,
              selectedIds: selectedInsightIds,
              onToggle: (insightId, selected) => {
                setSelectedInsightIds((current) => {
                  const next = new Set(current);
                  if (selected) next.add(insightId);
                  else next.delete(insightId);
                  return next;
                });
              },
              onToggleAll: (selected) => {
                setSelectedInsightIds((current) => {
                  const next = new Set(current);
                  for (const insight of rows) {
                    if (selected) next.add(insight.insight_id);
                    else next.delete(insight.insight_id);
                  }
                  return next;
                });
              },
            }}
          />
        )}
      </AsyncBlock>
      {duplicateListInsight.error ? <ErrorBanner message={duplicateListInsight.error.message} /> : null}
    </Page>
  );
}

function InsightReadView({ projectId, insightRef }: { projectId: string; insightRef: string }) {
  const { can } = useAuth();
  const selected = useQuery({
    queryKey: ["insight", insightRef],
    queryFn: () => getInsight(insightRef),
  });
  const result = useQuery({
    queryKey: ["insight-result", projectId, selected.data?.insight_id],
    queryFn: () => executeInsight({ insightId: selected.data!.insight_id, projectId }),
    enabled: Boolean(selected.data?.insight_id),
    retry: false,
  });

  if (selected.isLoading) {
    return <Page title="Insight" subtitle="Loading saved insight…"><p className="text-sm text-[#657082]">Loading insight…</p></Page>;
  }
  if (selected.error || !selected.data) {
    return <Page title="Insight" subtitle="The saved insight could not be loaded."><ErrorBanner message={(selected.error as Error | null)?.message ?? "Insight not found."} /></Page>;
  }

  const insight = selected.data;
  const config: InsightDraft = {
    version: 2,
    name: insight.name,
    query: insight.query,
    view: insight.view,
  };
  return (
    <div className="flex h-[calc(100vh-104px)] min-h-[520px] flex-col gap-4">
      <section className="shrink-0 border-b border-[#dce3eb] pb-4">
        <div className="flex items-start gap-3">
          <Button size="icon" variant="ghost" onClick={() => (window.location.href = `/project/${projectId}/insights`)}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <InsightViewThumbnail className="mt-0.5 h-10 w-14" decorative kind={insight.view.kind} />
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-xl font-semibold text-[#1d2430]">{insight.name}</h1>
            {insight.description?.trim() ? (
              <p className="mt-2 max-w-[860px] text-sm text-[#526071]">{insight.description}</p>
            ) : null}
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button aria-label="Insight actions" size="icon" variant="ghost">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                disabled={!can("insight.edit", projectId)}
                onClick={() => {
                  window.location.href = `/project/${projectId}/insights/${encodeURIComponent(insight.url_slug)}/edit`;
                }}
              >
                <Pencil className="h-4 w-4" /> Edit details
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </section>
      <div className="min-h-0 flex-1">
        {result.isLoading ? (
          <Card className="mt-0 grid h-full min-h-[320px] place-items-center text-sm text-[#657082]">Loading insight preview…</Card>
        ) : (
          <InsightPreviewPanel
            config={config as unknown as Record<string, unknown>}
            error={result.error instanceof Error ? result.error : null}
            result={result.data}
            setupWarning={null}
          />
        )}
      </div>
    </div>
  );
}

function InsightBuilder({
  projectId,
  target,
}: {
  projectId: string;
  target: Extract<InsightTarget, { mode: "new" } | { mode: "edit" }>;
}) {
  const { can } = useAuth();
  const insightRef = target.mode === "new" ? null : target.insightRef;
  const selected = useQuery({
    queryKey: ["insight", insightRef],
    queryFn: () => getInsight(insightRef ?? ""),
    enabled: Boolean(insightRef),
  });
  const [draft, setDraft] = useState<InsightDraft>(() => {
    return emptyInsightDraft(target.mode === "new" ? target.queryKind : undefined);
  });
  const [description, setDescription] = useState("");
  const [descriptionOpen, setDescriptionOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const familyDrafts = useRef<Partial<Record<QueryKind, QueryNode>>>({});

  useEffect(() => {
    if (!selected.data) return;
    setDraft({ version: 2, name: selected.data.name, query: selected.data.query, view: selected.data.view });
    setDescription(selected.data.description ?? "");
    setDescriptionOpen(Boolean(selected.data.description));
    familyDrafts.current = { [selected.data.query.kind]: selected.data.query };
  }, [selected.data]);

  const fields = useQuery({
    queryKey: ["catalog-fields", projectId, draft.query.kind],
    queryFn: async () => {
      const result = await searchCatalogFields(projectId, draft.query.kind);
      return ((result as { items?: CatalogField[] }).items ?? []);
    },
  });
  const datasets = useQuery({
    queryKey: ["catalog-datasets", projectId],
    queryFn: async () => {
      const result = await listCatalogDatasets(projectId);
      return ((result as { items?: CatalogDataset[] }).items ?? []);
    },
  });
  const datasetNames = useMemo(
    () => Object.fromEntries((datasets.data ?? []).map((dataset) => [dataset.data_contract_id, dataset.name])),
    [datasets.data],
  );
  const parsed = insightDefinitionSchema.safeParse(draft);
  const validation = useQuery({
    queryKey: ["insight-v2-validation", projectId, draft],
    queryFn: () => validateInsightConfig({ ...draft, project_id: projectId }),
    enabled: parsed.success,
    retry: false,
  });
  const preview = useQuery({
    queryKey: ["insight-v2-preview", projectId, draft],
    queryFn: () => executeInsight({ projectId, config: draft, description, refresh: true }),
    enabled: validation.data?.valid === true,
    retry: false,
  });
  const fingerprint = typeof preview.data?.preview_fingerprint === "string" ? preview.data.preview_fingerprint : null;
  const maySave = selected.data ? can("insight.edit", projectId) : true;
  const save = useMutation({
    mutationFn: async () => {
      if (!fingerprint) throw new Error("Preview this exact query before saving.");
      if (selected.data) return patchInsight(selected.data.insight_id, { ...draft, description, preview_fingerprint: fingerprint });
      return createInsight({ ...draft, project_id: projectId, description, preview_fingerprint: fingerprint });
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["insights", projectId] });
      window.location.href = `/project/${projectId}/insights/${saved.url_slug}`;
    },
  });

  if (selected.isLoading) return <Page title="Insight" subtitle="Loading semantic definition…"><p className="text-sm text-[#657082]">Loading insight…</p></Page>;
  if (selected.error) return <Page title="Insight" subtitle="The saved definition could not be loaded."><ErrorBanner message={(selected.error as Error).message} /></Page>;

  const error = parsed.success && validation.data && !validation.data.valid
      ? String(validation.data.messages[0]?.message ?? "Invalid query")
      : preview.error instanceof Error
        ? preview.error.message
        : null;

  const switchFamily = (kind: QueryKind) => {
    familyDrafts.current[draft.query.kind] = draft.query;
    const cached = familyDrafts.current[kind];
    if (cached) {
      setDraft((current) => ({ ...current, query: cached, view: createView(kind, current.view.kind) }));
      return;
    }
    setDraft((current) => switchQueryFamily(current, kind));
  };
  const updateQuery = (query: QueryNode) => {
    familyDrafts.current[query.kind] = query;
    setDraft((current) => ({ ...current, query }));
  };
  const changeView = (kind: ViewKind) => setDraft((current) => ({ ...current, view: createView(current.query.kind, kind) }));

  return (
    <div className="flex h-[calc(100vh-48px)] min-h-0 flex-col gap-3">
      <InsightBuilderHeader
        name={draft.name}
        description={description}
        descriptionOpen={descriptionOpen}
        isSaving={save.isPending}
        canSave={maySave && Boolean(fingerprint)}
        showSave={maySave}
        onBack={() => {
          window.location.href = selected.data?.url_slug
            ? `/project/${projectId}/insights/${encodeURIComponent(selected.data.url_slug)}`
            : `/project/${projectId}/insights`;
        }}
        onDescriptionChange={setDescription}
        onDescriptionOpenChange={setDescriptionOpen}
        onNameChange={(name) => setDraft((current) => ({ ...current, name }))}
        onSave={() => save.mutate()}
        onSaveContinue={() => save.mutate()}
      />
      <BuilderToolbar
        advancedOpen={advancedOpen}
        draft={draft}
        readOnly={false}
        onAdvancedOpenChange={setAdvancedOpen}
        onChange={setDraft}
        onChangeFamily={switchFamily}
        onChangeView={changeView}
      />
      {error ? <ErrorBanner message={error} /> : null}
      {save.error instanceof Error ? <ErrorBanner message={save.error.message} /> : null}
      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[376px_minmax(0,1fr)]">
        <Card className="mt-0 min-h-0 overflow-auto">
          <CardContent className="space-y-5 p-5">
            <FamilyEditor
              advancedOpen={advancedOpen}
              datasetNames={datasetNames}
              disabled={false}
              draft={draft}
              fields={fields.data ?? []}
              fieldsLoading={fields.isLoading}
              update={updateQuery}
              updateView={(view) => setDraft((current) => ({ ...current, view }))}
            />
          </CardContent>
        </Card>
        <div className="flex min-h-0 flex-col">
          <div className="min-h-0 flex-1">
            <InsightPreviewPanel
              config={draft as unknown as Record<string, unknown>}
              error={preview.error instanceof Error ? preview.error : null}
              result={preview.data}
              setupWarning={validation.data?.valid ? null : "Choose the required fields to preview this insight."}
              toolbar={
                <ViewPicker compact disabled={false} kind={draft.view.kind} queryKind={draft.query.kind} onChange={changeView} />
              }
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function BuilderToolbar({
  advancedOpen,
  draft,
  readOnly,
  onAdvancedOpenChange,
  onChange,
  onChangeFamily,
  onChangeView,
}: {
  advancedOpen: boolean;
  draft: InsightDraft;
  readOnly: boolean;
  onAdvancedOpenChange: (open: boolean) => void;
  onChange: (draft: InsightDraft) => void;
  onChangeFamily: (kind: QueryKind) => void;
  onChangeView: (kind: ViewKind) => void;
}) {
  const identity = queryIdentity(draft.query);
  return (
    <section className="flex shrink-0 flex-wrap items-end gap-2 border-b border-[#dce3eb] pb-2">
      <AnalysisTypePicker disabled={readOnly} kind={draft.query.kind} onChange={onChangeFamily} />
      {identity ? (
        <ToolbarField label={identity.label}>
          <div className="relative">
            <Users className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-[#657082]" />
            <select
              className="h-10 min-w-[160px] appearance-none rounded-md border border-[#ccd6e2] bg-white pl-9 pr-8 text-sm font-medium text-[#253343] disabled:opacity-50"
              disabled={readOnly}
              value={identity.value}
              onChange={(event) => onChange({ ...draft, query: identity.update(event.target.value as Grain) })}
            >
              {GRAINS.map((grain) => <option key={grain} value={grain}>{titleCase(`${grain}s`)}</option>)}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-3 h-4 w-4 text-[#657082]" />
          </div>
        </ToolbarField>
      ) : null}
      <ToolbarField label="View as">
        <ViewPicker disabled={readOnly} kind={draft.view.kind} queryKind={draft.query.kind} onChange={onChangeView} />
      </ToolbarField>
      <div className="ml-auto flex items-center gap-1">
        <Button className={advancedOpen ? "bg-[#eef5f1]" : ""} variant="ghost" onClick={() => onAdvancedOpenChange(!advancedOpen)}><Settings2 className="h-4 w-4" /> Settings</Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild><Button aria-label="Insight actions" size="icon" variant="outline"><MoreHorizontal className="h-4 w-4" /></Button></DropdownMenuTrigger>
          <DropdownMenuContent align="end"><DropdownMenuItem onClick={() => onAdvancedOpenChange(true)}>Open advanced settings</DropdownMenuItem></DropdownMenuContent>
        </DropdownMenu>
      </div>
    </section>
  );
}

function FamilyEditor({
  advancedOpen,
  datasetNames,
  disabled,
  draft,
  fields,
  fieldsLoading,
  update,
  updateView,
}: {
  advancedOpen: boolean;
  datasetNames: Record<string, string>;
  disabled: boolean;
  draft: InsightDraft;
  fields: CatalogField[];
  fieldsLoading: boolean;
  update: (query: QueryNode) => void;
  updateView: (view: InsightDraft["view"]) => void;
}) {
  if (draft.query.kind === "rows") return <RowsEditor advancedOpen={advancedOpen} datasetNames={datasetNames} disabled={disabled} draft={draft} fields={fields} fieldsLoading={fieldsLoading} update={update} updateView={updateView} />;
  if (draft.query.kind === "summary") return <SummaryEditor advancedOpen={advancedOpen} datasetNames={datasetNames} disabled={disabled} draft={draft} fields={fields} fieldsLoading={fieldsLoading} update={update} />;
  return <RoleBasedEditor advancedOpen={advancedOpen} datasetNames={datasetNames} disabled={disabled} draft={draft} fields={fields} fieldsLoading={fieldsLoading} update={update} />;
}

function RowsEditor({ advancedOpen, datasetNames, disabled, draft, fields, fieldsLoading, update, updateView }: EditorProps) {
  const query = draft.query;
  if (query.kind !== "rows") return null;
  const [dragged, setDragged] = useState<number | null>(null);
  const selected = query.columns.map(selectionReference);
  return (
    <section className="space-y-3">
      <EditorHeading title="Columns" subtitle={`Row identity: ${titleCase(query.grain)}`} />
      {!query.columns.length ? (
        <div className="rounded-lg border border-dashed border-[#cbd6e2] bg-[#f8fafc] px-5 py-7 text-center">
          <p className="m-0 text-sm font-semibold text-[#526071]">Add columns to build this table.</p>
          <p className="mb-0 mt-1 text-xs leading-5 text-[#758195]">Results and project metadata can be used together.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {query.columns.map((column, index) => {
            const reference = selectionReference(column);
            const field = selectedCatalogField(column, fields);
            return (
              <InsightFieldCard
                field={field}
                hidden={(draft.view.hidden_values ?? []).includes(reference)}
                key={`${reference}:${index}`}
                label={column.label || field?.display_name || column.field}
                readOnly={disabled}
                onDragStart={() => setDragged(index)}
                onDrop={() => {
                  if (dragged === null || dragged === index) return;
                  const columns = [...query.columns];
                  const [moved] = columns.splice(dragged, 1);
                  columns.splice(index, 0, moved);
                  update({ ...query, columns });
                  setDragged(null);
                }}
                onRemove={() => update({ ...query, columns: query.columns.filter((_, itemIndex) => itemIndex !== index) })}
                onToggleVisibility={() => updateView && toggleVisibility(draft, reference, updateView)}
              />
            );
          })}
        </div>
      )}
      <InsightFieldPicker
        button={<Button disabled={disabled || fieldsLoading} variant="outline"><Plus className="h-4 w-4" /> {fieldsLoading ? "Loading fields…" : "Add columns"}</Button>}
        datasetNames={datasetNames}
        disabled={disabled || fieldsLoading}
        fields={fields.filter((field) => !selected.includes(field.field))}
        mode="multiple"
        selected={selected}
        title="Add columns"
        onSelect={(chosen) => update({ ...query, columns: [...query.columns, ...chosen.map((field) => catalogSelection(field))] })}
      />
      {advancedOpen ? <AdvancedSettings query={query} disabled={disabled} update={update} /> : null}
    </section>
  );

}

function SummaryEditor({ advancedOpen, datasetNames, disabled, draft, fields, fieldsLoading, update }: EditorProps) {
  const query = draft.query;
  if (query.kind !== "summary") return null;
  const groups = query.group_by ?? [];
  const aggregation = query.aggregations[0];
  return (
    <section className="space-y-5">
      <FieldRoleSection title="Group by" subtitle="Optional categories that define each summary row.">
        {groups.map((selection, index) => (
          <RoleField key={`${selectionReference(selection)}:${index}`} datasetNames={datasetNames} disabled={disabled} field={selection} fields={fields} label="Group" onChange={(next) => update({ ...query, group_by: groups.map((item, itemIndex) => itemIndex === index ? next : item) })} onRemove={() => update({ ...query, group_by: groups.filter((_, itemIndex) => itemIndex !== index) })} />
        ))}
        {!groups.length ? <RoleAddButton datasetNames={datasetNames} disabled={disabled || fieldsLoading} fields={fields} label="Add group" title="Choose a grouping field" onSelect={(field) => update({ ...query, group_by: [catalogSelection(field)] })} /> : null}
      </FieldRoleSection>
      <FieldRoleSection title="Values" subtitle="Descriptive calculations performed for each group.">
        <RoleField datasetNames={datasetNames} disabled={disabled} field={aggregation} fields={fields} label="Measure" onChange={(next) => update({ ...query, aggregations: [{ ...aggregation, ...next }] })} />
        <label className="block text-xs font-semibold uppercase tracking-wide text-[#657082]">Calculation
          <select className="mt-1 h-9 w-full rounded-md border border-[#d6dee8] bg-white px-2 text-sm" disabled={disabled} value={aggregation.aggregation} onChange={(event) => update({ ...query, aggregations: [{ ...aggregation, aggregation: event.target.value as typeof aggregation.aggregation }] })}>
            {(["count", "count_distinct", "sum", "avg", "min", "max"] as const).map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}
          </select>
        </label>
      </FieldRoleSection>
      {advancedOpen ? <AdvancedSettings query={query} disabled={disabled} update={update} /> : null}
    </section>
  );
}

function RoleBasedEditor({ advancedOpen, datasetNames, disabled, draft, fields, fieldsLoading, update }: EditorProps) {
  const query = draft.query;
  const meta = analysisType(query.kind);
  return (
    <section className="space-y-5">
      <EditorHeading title={meta.label} subtitle={meta.description} />
      <div className="space-y-4">
        {querySlots(query).map(({ key, label, value }) => (
          <FieldRoleSection key={key} title={label}>
            <RoleField datasetNames={datasetNames} disabled={disabled || fieldsLoading} field={value} fields={fields} label={label} onChange={(field) => update(updateQuerySlot(query, key, field))} />
          </FieldRoleSection>
        ))}
      </div>
      {query.kind === "alteration_matrix" || query.kind === "association" ? (
        <label className="block text-xs font-semibold uppercase tracking-wide text-[#657082]">Features
          <Input className="mt-1" disabled={disabled} value={query.features.join(", ")} placeholder="TP53, KRAS" onChange={(event) => update({ ...query, features: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} />
        </label>
      ) : null}
      {query.kind === "survival" ? <div className="rounded-md border border-[#f5d58a] bg-[#fff9e9] p-3 text-sm leading-5 text-[#7b5711]">Kaplan–Meier estimation and significance testing require a registered analysis provider or a precomputed result.</div> : null}
      {advancedOpen ? <AdvancedSettings query={query} disabled={disabled} update={update} /> : null}
    </section>
  );
}

type EditorProps = {
  advancedOpen: boolean;
  datasetNames: Record<string, string>;
  disabled: boolean;
  draft: InsightDraft;
  fields: CatalogField[];
  fieldsLoading: boolean;
  update: (query: QueryNode) => void;
  updateView?: (view: InsightDraft["view"]) => void;
};

function RoleField({ datasetNames, disabled, field, fields, label, onChange, onRemove }: { datasetNames: Record<string, string>; disabled: boolean; field: FieldSelection; fields: CatalogField[]; label: string; onChange: (field: FieldSelection) => void; onRemove?: () => void }) {
  const catalogField = selectedCatalogField(field, fields);
  return (
    <InsightFieldPicker
      button={(open) => <InsightFieldCard field={catalogField} label={field.label || catalogField?.display_name || (field.field ? field.field : `Choose ${label.toLowerCase()}`)} onRemove={onRemove} onReplace={open} readOnly={disabled} />}
      datasetNames={datasetNames}
      disabled={disabled}
      fields={fields}
      selected={field.field ? [field.field] : []}
      title={`Choose ${label.toLowerCase()}`}
      onSelect={([selected]) => selected && onChange(catalogSelection(selected, field))}
    />
  );
}

function RoleAddButton({ datasetNames, disabled, fields, label, onSelect, title }: { datasetNames: Record<string, string>; disabled: boolean; fields: CatalogField[]; label: string; onSelect: (field: CatalogField) => void; title: string }) {
  return <InsightFieldPicker button={<Button disabled={disabled} variant="outline"><Plus className="h-4 w-4" /> {label}</Button>} datasetNames={datasetNames} disabled={disabled} fields={fields} title={title} onSelect={([field]) => field && onSelect(field)} />;
}

function AdvancedSettings({ query, disabled, update }: { query: QueryNode; disabled: boolean; update: (query: QueryNode) => void }) {
  return (
    <section className="rounded-lg border border-[#dce3eb] bg-[#f8fafc] p-3">
      <h3 className="m-0 text-xs font-bold uppercase tracking-wide text-[#526071]">Advanced settings</h3>
      <label className="mt-3 block text-sm font-medium text-[#253343]">Inline row limit
        <Input className="mt-1 bg-white" type="number" min={1} max={10_000} disabled={disabled} value={query.limit ?? 1_000} onChange={(event) => update({ ...query, limit: Number(event.target.value) } as QueryNode)} />
      </label>
      <p className="mb-0 mt-2 text-xs leading-5 text-[#758195]">Exports can include the full contributing data. Inline previews remain bounded.</p>
    </section>
  );
}

function EditorHeading({ subtitle, title }: { subtitle?: string; title: string }) {
  return <div><h2 className="m-0 text-xs font-bold uppercase tracking-wide text-[#526071]">{title}</h2>{subtitle ? <p className="mb-0 mt-0.5 text-xs leading-5 text-[#758195]">{subtitle}</p> : null}</div>;
}

function FieldRoleSection({ children, subtitle, title }: { children: ReactNode; subtitle?: string; title: string }) {
  return <section className="space-y-2"><EditorHeading subtitle={subtitle} title={title} />{children}</section>;
}

function queryIdentity(query: QueryNode): { label: string; value: Grain; update: (grain: Grain) => QueryNode } | null {
  if (query.kind === "rows" || query.kind === "summary") return { label: "Analyze by", value: query.grain, update: (grain) => ({ ...query, grain }) };
  if (query.kind === "relationship") return { label: "Match by", value: query.match_by, update: (grain) => ({ ...query, match_by: grain }) };
  return null;
}

function querySlots(query: QueryNode): { key: string; label: string; value: FieldSelection }[] {
  switch (query.kind) {
    case "relationship": return [{ key: "x", label: "X axis", value: query.x }, { key: "y", label: "Y axis", value: query.y }];
    case "distribution": return [{ key: "value", label: "Value", value: query.value }];
    case "series": return [{ key: "position", label: "Position", value: query.position }, { key: "measurements", label: "Measurement", value: query.measurements[0] }];
    case "matrix": return [{ key: "rows", label: "Rows", value: query.rows }, { key: "columns", label: "Columns", value: query.columns }, { key: "value", label: "Raw value", value: query.value }];
    case "alteration_matrix": return [{ key: "alterations", label: "Alteration state", value: query.alterations[0] }];
    case "variant_position": return [{ key: "position", label: "Position", value: query.position }, { key: "frequency", label: "Frequency", value: query.frequency }];
    case "genome_profile": return [{ key: "coordinate", label: "Coordinate", value: query.coordinate }, { key: "value", label: "Value", value: query.value }];
    case "survival": return [{ key: "duration", label: "Duration", value: query.duration }, { key: "event", label: "Event", value: query.event }];
    case "timeline": return [{ key: "subject", label: "Subject", value: query.subject }, { key: "start", label: "Start", value: query.start }];
    case "association": return [{ key: "state", label: "State", value: query.state[0] }];
    default: return [];
  }
}

function updateQuerySlot(query: QueryNode, key: string, field: FieldSelection): QueryNode {
  if (key === "measurements" && query.kind === "series") return { ...query, measurements: [field] };
  if (key === "alterations" && query.kind === "alteration_matrix") return { ...query, alterations: [field] };
  if (key === "state" && query.kind === "association") return { ...query, state: [field] };
  return { ...query, [key]: field } as QueryNode;
}

function selectionReference(field: FieldSelection) {
  return field.as || field.field;
}

function toggleVisibility(draft: InsightDraft, reference: string, onChange: (view: InsightDraft["view"]) => void) {
  const hidden = new Set(draft.view.hidden_values ?? []);
  if (hidden.has(reference)) hidden.delete(reference);
  else hidden.add(reference);
  onChange({ ...draft.view, hidden_values: [...hidden] });
}

function filterInsights(insights: InsightSummary[], search: string) {
  const term = search.trim().toLowerCase();
  if (!term) return insights;
  return insights.filter((insight) => [insight.name, insight.description, insight.insight_id].filter(Boolean).some((value) => String(value).toLowerCase().includes(term)));
}

function ErrorBanner({ message }: { message: string }) {
  return <div className="rounded-md border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-sm text-[#b42318]">{message}</div>;
}
