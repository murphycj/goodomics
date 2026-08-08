import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, BarChart3, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  bulkDeleteInsights,
  createInsight,
  deleteInsight,
  duplicateInsight,
  executeInsight,
  getInsight,
  getInsightCapabilities,
  listInsights,
  listProjectDataContracts,
  listReports,
  patchInsight,
  renameInsight,
  validateInsightConfig,
  type InsightSummary,
} from "../api";
import { useAuth } from "../components/auth/AuthProvider";
import { InsightBuilderHeader } from "../components/insights/InsightBuilderHeader";
import { InsightBuilderToolbar } from "../components/insights/InsightBuilderToolbar";
import { InsightPreviewPanel } from "../components/insights/InsightPreviewPanel";
import { InsightValueEditor } from "../components/insights/InsightValueEditor";
import { buildInsightPickerOptions } from "../components/insights/InsightValuePicker";
import {
  ResultScopeEditor,
  type ResultScope as EditorScope,
} from "../components/insights/ResultScopeEditor";
import { InsightListTable } from "../components/reports/InsightListTable";
import { SavedItemRenameDialog } from "../components/reports/SavedItemRenameDialog";
import {
  AsyncBlock,
  Button,
  Card,
  CardContent,
  ConfirmDialog,
  Input,
  Page,
} from "../components/ui";
import {
  insightDefinitionSchema,
  type InsightDraft,
  type InsightView,
  type ResultScope,
} from "../lib/insightSchemas";
import {
  createViewForKind,
  defaultScope,
  reconcileView,
} from "../lib/insightBuilder";
import { parseFieldReference, valueReference } from "../lib/fieldReferences";
import { getInsightViewDefinition } from "../lib/insightViewCatalog";
import { queryClient } from "../lib/queryClient";

type InsightTarget =
  | { mode: "list" }
  | { mode: "new" }
  | { mode: "view"; insightRef: string }
  | { mode: "edit"; insightRef: string };

const emptyDraft = (): InsightDraft => ({
  version: 1,
  analysis: {
    grain: "sample",
    values: [],
    filters: [],
    match_by: "sample",
    join: "outer",
    limit: 1_000,
    random: false,
  },
  view: {
    kind: "table",
    hidden_values: [],
    sorting: [],
    null_format: "—",
    numeric_format: {},
  },
});

/** Values-only insight index and builder. */
export function InsightsPage({
  projectId,
  target = { mode: "list" },
}: {
  projectId: string;
  target?: InsightTarget;
}) {
  const { can } = useAuth();
  const insights = useQuery({
    queryKey: ["insights", projectId],
    queryFn: () => listInsights(projectId),
  });
  const reports = useQuery({
    queryKey: ["reports", projectId],
    queryFn: () => listReports(projectId),
  });
  const contracts = useQuery({
    queryKey: ["data-contracts", projectId],
    queryFn: () => listProjectDataContracts(projectId),
  });
  const capabilities = useQuery({
    queryKey: ["insight-capabilities"],
    queryFn: getInsightCapabilities,
  });
  const selectedInsightRef = target.mode === "edit" || target.mode === "view"
    ? target.insightRef
    : null;
  const selected = useQuery({
    queryKey: ["insight", selectedInsightRef],
    queryFn: () => getInsight(selectedInsightRef ?? ""),
    enabled: Boolean(selectedInsightRef),
  });
  const [search, setSearch] = useState("");
  const [selectedInsightIds, setSelectedInsightIds] = useState<Set<string>>(new Set());
  const [renameTarget, setRenameTarget] = useState<InsightSummary | null>(null);
  const [deleteTargets, setDeleteTargets] = useState<InsightSummary[]>([]);
  const [bulkInsightDelete, setBulkInsightDelete] = useState(false);
  const [name, setName] = useState("New insight");
  const [description, setDescription] = useState("");
  const [descriptionOpen, setDescriptionOpen] = useState(false);
  const [draft, setDraft] = useState<InsightDraft>(emptyDraft);
  const [scopeValueId, setScopeValueId] = useState<string | null>(null);
  const viewHistory = useRef<Partial<Record<InsightView["kind"], InsightView>>>({});

  useEffect(() => {
    if (!selected.data) return;
    setName(selected.data.name);
    setDescription(selected.data.description ?? "");
    setDescriptionOpen(Boolean(selected.data.description));
    setDraft({
      version: 1,
      analysis: selected.data.analysis,
      view: selected.data.view,
    });
    viewHistory.current = {};
  }, [selected.data]);

  const pickerOptions = useMemo(
    () => buildInsightPickerOptions(
      contracts.data ?? [],
      capabilities.data?.metadata_fields ?? [],
      capabilities.data?.aggregations_by_type ?? {},
      defaultScope(draft.analysis.grain),
    ),
    [capabilities.data?.aggregations_by_type, capabilities.data?.metadata_fields, contracts.data, draft.analysis.grain],
  );
  const parsedDraft = insightDefinitionSchema.safeParse(draft);
  const validation = useQuery({
    queryKey: ["insight-validation", projectId, draft],
    queryFn: () => validateInsightConfig({ ...draft, project_id: projectId }),
    enabled: parsedDraft.success,
    retry: false,
  });
  const preview = useQuery({
    queryKey: ["insight-preview", projectId, draft, name, description],
    queryFn: () =>
      executeInsight({ projectId, config: draft, name, description, refresh: true }),
    enabled: validation.data?.valid === true,
    retry: false,
  });
  const savedInsightId = selected.data?.insight_id;
  const maySave = savedInsightId ? can("insight.edit", projectId) : true;
  const canSave = maySave && Boolean(name.trim()) && validation.data?.valid === true;
  const save = useMutation({
    mutationFn: async (continueEditing: boolean) => {
      const complete = insightDefinitionSchema.parse(draft);
      const saved = savedInsightId
        ? await patchInsight(savedInsightId, {
            ...complete,
            name: name.trim(),
            description: description || null,
          })
        : await createInsight({
            ...complete,
            project_id: projectId,
            name: name.trim(),
            description: description || null,
          });
      return { continueEditing, saved };
    },
    onSuccess: ({ continueEditing, saved }) => {
      void queryClient.invalidateQueries({ queryKey: ["insights", projectId] });
      window.location.href = continueEditing
        ? `/project/${projectId}/insights/${encodeURIComponent(saved.url_slug)}/edit`
        : `/project/${projectId}/insights`;
    },
  });
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
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["insights", projectId] });
    },
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

  if (target.mode === "list") {
    const rows = filterInsights(insights.data ?? [], search);
    const selectedRows = (insights.data ?? []).filter((insight) =>
      selectedInsightIds.has(insight.insight_id),
    );
    const canEditInsights = can("insight.edit", projectId);
    const canDeleteInsights = can("insight.delete", projectId);
    return (
      <Page title="Insights" subtitle="Create reusable values, tables, and charts.">
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
            if (renameTarget) {
              renameListInsight.mutate({
                insightId: renameTarget.insight_id,
                nextName,
              });
            }
          }}
        />
        <ConfirmDialog
          confirmLabel={deleteTargets.length > 1 ? "Delete insights" : "Delete insight"}
          description={
            bulkInsightDelete
              ? `Delete ${deleteTargets.length} selected ${deleteTargets.length === 1 ? "insight" : "insights"}? This action cannot be undone.`
              : `Delete “${deleteTargets[0]?.name ?? "this insight"}”? This action cannot be undone.`
          }
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
                <span className="text-sm text-[#657082]">
                  {selectedRows.length} selected
                </span>
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
            <Button onClick={() => (window.location.href = `/project/${projectId}/insights/new`)}>
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
                onRename: (insight) => setRenameTarget(insight),
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
        {duplicateListInsight.error ? (
          <ErrorBanner message={duplicateListInsight.error.message} />
        ) : null}
      </Page>
    );
  }

  if (target.mode === "view") {
    if (selected.error) {
      return <ErrorBanner message={(selected.error as Error).message} />;
    }
    if (selected.isLoading || !selected.data) {
      return <div className="p-4 text-sm text-[#657082]">Loading insight…</div>;
    }
    return (
      <div className="flex h-[calc(100vh-48px)] min-h-0 flex-col gap-4">
        <section className="shrink-0 border-b border-[#dce3eb] pb-4">
          <div className="flex items-start gap-3">
            <Button size="icon" variant="ghost" onClick={() => { window.location.href = `/project/${projectId}/insights`; }}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <BarChart3 className="mt-2 h-5 w-5 shrink-0 text-[#16784a]" />
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-xl font-semibold text-[#1d2430]">{selected.data.name}</h1>
              {selected.data.description ? (
                <p className="mt-2 max-w-[860px] text-sm text-[#526071]">{selected.data.description}</p>
              ) : null}
            </div>
            {can("insight.edit", projectId) ? (
              <Button
                variant="outline"
                onClick={() => {
                  window.location.href = `/project/${projectId}/insights/${encodeURIComponent(selected.data.url_slug)}/edit`;
                }}
              >
                <Pencil className="h-4 w-4" /> Edit
              </Button>
            ) : null}
          </div>
        </section>
        <div className="min-h-0 flex-1">
          <InsightPreviewPanel
            config={draft as unknown as Record<string, unknown>}
            error={(preview.error as Error | null) ?? null}
            result={preview.data}
            setupWarning={preview.isLoading ? "Loading insight…" : null}
          />
        </div>
      </div>
    );
  }

  const activeScopeValue = draft.analysis.values.find((value) => {
    if (valueReference(value) !== scopeValueId) return false;
    return parseFieldReference(value.field).kind === "contract";
  });
  const activeScopeReference = activeScopeValue
    ? parseFieldReference(activeScopeValue.field)
    : null;
  const activeContract = contracts.data?.find(
    (contract) =>
      activeScopeReference?.kind === "contract"
      && contract.data_contract_id === activeScopeReference.contractId,
  );

  return (
    <div className="flex h-[calc(100vh-48px)] min-h-0 flex-col gap-3">
      <InsightBuilderHeader
        name={name}
        description={description}
        descriptionOpen={descriptionOpen}
        isSaving={save.isPending}
        canSave={canSave}
        showSave={maySave}
        onBack={() => (window.location.href = `/project/${projectId}/insights`)}
        onDescriptionChange={setDescription}
        onDescriptionOpenChange={setDescriptionOpen}
        onNameChange={setName}
        onSave={() => save.mutate(false)}
        onSaveContinue={() => save.mutate(true)}
      />
      <InsightBuilderToolbar
        draft={draft}
        result={preview.data}
        templates={capabilities.data?.templates ?? []}
        onChange={setDraft}
        onClearValues={() => {
          viewHistory.current = {};
          setDraft((current) => ({
            ...current,
            analysis: { ...current.analysis, values: [] },
            view: createViewForKind(current.view.kind, []),
          }));
        }}
        onDescription={() => setDescriptionOpen(true)}
        onGrainChange={(grain) => {
          setDraft((current) => {
            const previousDefault = current.analysis.grain === "run"
              ? "all_eligible"
              : "latest_successful_per_sample";
            const nextValues = current.analysis.values.map((value) => {
              if (
                parseFieldReference(value.field).kind !== "contract"
                || value.scope?.selection !== previousDefault
              ) return value;
              return { ...value, scope: defaultScope(grain) };
            });
            return {
              ...current,
              analysis: { ...current.analysis, grain, match_by: grain, values: nextValues },
              view: reconcileView(current.view, nextValues, grain),
            };
          });
        }}
        onTemplate={(template) => {
          setDraft((current) => {
            const grain = template.grain ?? current.analysis.grain;
            const kind = template.viewKind ?? current.view.kind;
            const previousDefault = current.analysis.grain === "run"
              ? "all_eligible"
              : "latest_successful_per_sample";
            const values = current.analysis.values.map((value) => {
              if (
                parseFieldReference(value.field).kind !== "contract"
                || value.scope?.selection !== previousDefault
              ) return value;
              return { ...value, scope: defaultScope(grain) };
            });
            viewHistory.current = {};
            return {
              ...current,
              analysis: {
                ...current.analysis,
                grain,
                match_by: grain,
                join: getInsightViewDefinition(kind).defaultJoin,
                values,
              },
              view: createViewForKind(kind, values),
            };
          });
        }}
        onViewKindChange={(kind) => {
          setDraft((current) => {
            viewHistory.current[current.view.kind] = current.view;
            const remembered = viewHistory.current[kind];
            const view = reconcileView(
              remembered ?? createViewForKind(kind, current.analysis.values),
              current.analysis.values,
              current.analysis.grain,
            );
            return {
              ...current,
              analysis: {
                ...current.analysis,
                join: getInsightViewDefinition(kind).defaultJoin,
              },
              view,
            };
          });
        }}
      />
      {save.error instanceof Error ? <ErrorBanner message={save.error.message} /> : null}
      {!parsedDraft.success && draft.analysis.values.length ? (
        <ErrorBanner message={parsedDraft.error.issues[0]?.message ?? "Complete the insight."} />
      ) : validation.data && !validation.data.valid ? (
        <ErrorBanner message={String(validation.data.messages[0]?.message ?? "Invalid insight.")} />
      ) : null}
      <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Card className="mt-0 min-h-0 overflow-auto">
          <CardContent className="p-4">
            <InsightValueEditor
              draft={draft}
              options={pickerOptions}
              pickerStatus={
                contracts.isLoading || capabilities.isLoading
                  ? "loading"
                  : contracts.error || capabilities.error
                    ? "error"
                    : "ready"
              }
              onChange={setDraft}
              onEditScope={setScopeValueId}
            />
          </CardContent>
        </Card>
        <InsightPreviewPanel
          config={draft as unknown as Record<string, unknown>}
          error={(preview.error as Error | null) ?? null}
          result={preview.data}
          setupWarning={draft.analysis.values.length ? null : "Choose at least one value."}
        />
      </div>
      {activeScopeValue ? (
        <ResultScopeEditor
          contract={activeContract}
          defaultSelection={draft.analysis.grain === "run" ? "all_eligible" : "latest_successful_per_sample"}
          projectId={projectId}
          open
          scope={scopeToEditor(activeScopeValue.scope, draft.analysis.grain)}
          onOpenChange={(open) => !open && setScopeValueId(null)}
          onChange={(scope) => {
            setDraft((current) => ({
              ...current,
              analysis: {
                ...current.analysis,
                values: current.analysis.values.map((value) =>
                  valueReference(value) === valueReference(activeScopeValue)
                    ? { ...value, scope: editorToScope(scope) }
                    : value,
                ),
              },
            }));
          }}
        />
      ) : null}
    </div>
  );
}

function scopeToEditor(
  scope: ResultScope | undefined,
  grain: InsightDraft["analysis"]["grain"],
): EditorScope {
  const current = scope ?? defaultScope(grain);
  return {
    selection: current.selection,
    analysisTypeIds: current.analysis_type_ids,
    methodIds: current.method_ids,
    methodVersions: current.method_versions,
    runIds: current.run_ids,
    statuses: current.statuses,
    startedAfter: current.started_after ?? "",
    endedBefore: current.ended_before ?? "",
    runContractIds: current.run_contract_ids,
  };
}

function editorToScope(scope: EditorScope): ResultScope {
  return {
    selection: scope.selection,
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

function filterInsights(insights: InsightSummary[], search: string) {
  const query = search.trim().toLowerCase();
  if (!query) return insights;
  return insights.filter((insight) =>
    [insight.name, insight.description, insight.insight_id]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query)),
  );
}

function ErrorBanner({ message }: { message: string }) {
  return <div className="rounded-md border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-sm text-[#b42318]">{message}</div>;
}
