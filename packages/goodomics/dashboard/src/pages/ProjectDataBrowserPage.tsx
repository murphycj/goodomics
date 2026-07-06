import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import {
  ArrowLeft,
  MoreVertical,
  Pencil,
  Plus,
  Save,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Column } from "react-data-grid";
import {
  addProjectSampleGroupMembers,
  createProjectSampleGroup,
  deleteProjectSampleGroup,
  listProjectRuns,
  listProjectSampleGroupMembers,
  listProjectSampleGroups,
  listProjectSamples,
  patchProjectSampleGroup,
  removeProjectSampleGroupMembers,
  type GoodomicsRun,
  type SampleGroupMember,
  type SampleListItem,
  type SampleSet,
} from "../api";
import {
  Button,
  DataGridShell,
  Dialog,
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
  type GridColumnOption,
} from "../components/ui";
import { queryClient } from "../lib/queryClient";
import { cn, formatDate } from "../lib/utils";

const DATA_PAGE_SIZE = 50;
const DATA_PAGE_SIZE_OPTIONS = [25, 50, 100, 250];
const PICKER_PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

type DataBrowserTab = "samples" | "sample-groups" | "runs";
type SampleGridRow = SampleListItem & { __rowId: string };
type RunGridRow = GoodomicsRun & { __rowId: string };
type SampleGroupGridRow = SampleSet & { __rowId: string };
type SampleGroupMemberGridRow = SampleGroupMember & { __rowId: string };
type SampleGroupEditorTarget =
  | { mode: "new" }
  | { group: SampleGroupGridRow; mode: "edit" | "view" };

const SAMPLE_COLUMN_OPTIONS: GridColumnOption[] = [
  { key: "sample", label: "Sample" },
  { key: "subject_id", label: "Subject" },
  { key: "latest_run", label: "Latest run" },
  { key: "latest_run_created_at", label: "Latest activity" },
  { key: "run_count", label: "Runs" },
];

const RUN_COLUMN_OPTIONS: GridColumnOption[] = [
  { key: "run", label: "Run" },
  { key: "assay", label: "Assay" },
  { key: "status", label: "Status" },
  { key: "created_at", label: "Created" },
  { key: "samples", label: "Samples" },
];

const SAMPLE_GROUP_COLUMN_OPTIONS: GridColumnOption[] = [
  { key: "name", label: "Name" },
  { key: "member_count", label: "Samples" },
  { key: "updated_at", label: "Updated" },
  { key: "created_at", label: "Created" },
  { key: "description", label: "Description" },
];

const SAMPLE_GROUP_MEMBER_COLUMN_OPTIONS: GridColumnOption[] = [
  { key: "sample", label: "Sample" },
  { key: "subject_id", label: "Subject" },
  { key: "run", label: "Run" },
  { key: "status", label: "Status" },
];

/** Route-backed data browser for project samples, sample groups, and runs. */
export function ProjectDataBrowserPage({
  activeTab,
  projectId,
}: {
  activeTab: DataBrowserTab;
  projectId: string;
}) {
  const navigate = useNavigate();
  const openTab = (tab: DataBrowserTab) => {
    if (tab === "samples") {
      void navigate({ to: "/project/$projectId/samples", params: { projectId } });
      return;
    }
    if (tab === "sample-groups") {
      void navigate({
        to: "/project/$projectId/sample-groups",
        params: { projectId },
      });
      return;
    }
    void navigate({ to: "/project/$projectId/runs", params: { projectId } });
  };

  return (
    <div className="flex h-[calc(100vh-48px)] min-h-0 flex-col overflow-hidden bg-white">
      <div className="flex min-h-[58px] shrink-0 items-end border-b border-[#dce3eb] px-6">
        <div className="flex flex-wrap items-end gap-7">
          {[
            ["samples", "Samples"],
            ["sample-groups", "Sample groups"],
            ["runs", "Runs"],
          ].map(([value, label]) => {
            const tab = value as DataBrowserTab;
            const active = activeTab === tab;
            return (
              <button
                key={value}
                className={cn(
                  "relative h-12 border-0 border-b-2 bg-transparent px-0 text-sm font-semibold tracking-normal transition-colors",
                  active
                    ? "border-[#16784a] text-[#16784a]"
                    : "border-transparent text-[#657082] hover:text-[#1f2937]",
                )}
                type="button"
                onClick={() => openTab(tab)}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        {activeTab === "samples" ? (
          <SamplesTab projectId={projectId} />
        ) : activeTab === "sample-groups" ? (
          <SampleGroupsTab projectId={projectId} />
        ) : (
          <RunsTab projectId={projectId} />
        )}
      </div>
    </div>
  );
}

/** Paginated sample grid tab. */
function SamplesTab({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DATA_PAGE_SIZE);
  const [search, setSearch] = useState("");
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set());
  const offset = page * pageSize;
  const samples = useQuery({
    queryKey: ["project-samples", projectId, offset, pageSize, search],
    queryFn: () =>
      listProjectSamples({ projectId, limit: pageSize, offset, search }),
    placeholderData: (previous) => previous,
  });
  const data = samples.data;
  const rows = useMemo<SampleGridRow[]>(
    () =>
      (data?.items ?? []).map((sample) => ({
        __rowId: sample.sample_id,
        ...sample,
      })),
    [data?.items],
  );
  const columns = useSampleColumns(hiddenColumns);
  const openSample = (row: SampleGridRow) => {
    void navigate({
      to: "/project/$projectId/samples/$sampleId",
      params: { projectId, sampleId: row.sample_id },
    });
  };

  return (
    <DataGridShell
      autoFocusSearch
      columnOptions={SAMPLE_COLUMN_OPTIONS}
      columns={columns}
      emptyMessage="No samples have been stored for this project yet."
      error={queryError(samples.error)}
      hiddenColumns={hiddenColumns}
      isFetching={samples.isFetching}
      isLoading={samples.isLoading}
      itemLabel="records"
      pageIndex={page}
      pageSize={data?.limit ?? pageSize}
      pageSizeOptions={DATA_PAGE_SIZE_OPTIONS}
      rowKeyGetter={(row) => row.__rowId}
      rows={rows}
      searchPlaceholder="Search samples..."
      searchValue={search}
      sortValueGetter={sampleSortValue}
      total={data?.total ?? 0}
      onHiddenColumnsChange={setHiddenColumns}
      onPageChange={setPage}
      onPageSizeChange={(nextPageSize) => {
        setPageSize(nextPageSize);
        setPage(0);
      }}
      onRowOpen={openSample}
      onSearchChange={(value) => {
        setSearch(value);
        setPage(0);
      }}
    />
  );
}

/** Paginated run grid tab. */
function RunsTab({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DATA_PAGE_SIZE);
  const [search, setSearch] = useState("");
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set());
  const offset = page * pageSize;
  const runs = useQuery({
    queryKey: ["project-runs", projectId, offset, pageSize, search],
    queryFn: () => listProjectRuns({ projectId, limit: pageSize, offset, search }),
    placeholderData: (previous) => previous,
  });
  const data = runs.data;
  const rows = useMemo<RunGridRow[]>(
    () =>
      (data?.items ?? []).map((run) => ({
        __rowId: run.run_id,
        ...run,
      })),
    [data?.items],
  );
  const columns = useRunColumns(hiddenColumns);
  const openRun = (row: RunGridRow) => {
    void navigate({
      to: "/project/$projectId/runs/$runId",
      params: { projectId, runId: row.run_id },
    });
  };

  return (
    <DataGridShell
      autoFocusSearch
      columnOptions={RUN_COLUMN_OPTIONS}
      columns={columns}
      emptyMessage="No runs have been stored for this project yet."
      error={queryError(runs.error)}
      hiddenColumns={hiddenColumns}
      isFetching={runs.isFetching}
      isLoading={runs.isLoading}
      itemLabel="runs"
      pageIndex={page}
      pageSize={data?.limit ?? pageSize}
      pageSizeOptions={DATA_PAGE_SIZE_OPTIONS}
      rowKeyGetter={(row) => row.__rowId}
      rows={rows}
      searchPlaceholder="Search runs..."
      searchValue={search}
      sortValueGetter={runSortValue}
      total={data?.total ?? 0}
      onHiddenColumnsChange={setHiddenColumns}
      onPageChange={setPage}
      onPageSizeChange={(nextPageSize) => {
        setPageSize(nextPageSize);
        setPage(0);
      }}
      onRowOpen={openRun}
      onSearchChange={(value) => {
        setSearch(value);
        setPage(0);
      }}
    />
  );
}

/** Paginated sample-group grid tab with create and edit flows. */
function SampleGroupsTab({ projectId }: { projectId: string }) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(DATA_PAGE_SIZE);
  const [search, setSearch] = useState("");
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(
    () => new Set(["created_at"]),
  );
  const [editorTarget, setEditorTarget] =
    useState<SampleGroupEditorTarget | null>(null);
  const offset = page * pageSize;
  const groups = useQuery({
    queryKey: ["sample-groups", projectId, offset, pageSize, search],
    queryFn: () =>
      listProjectSampleGroups({ projectId, limit: pageSize, offset, search }),
    placeholderData: (previous) => previous,
  });
  const data = groups.data;
  const rows = useMemo<SampleGroupGridRow[]>(
    () =>
      (data?.items ?? []).map((group) => ({
        __rowId: group.sample_set_id,
        ...group,
      })),
    [data?.items],
  );
  const columns = useSampleGroupColumns(hiddenColumns);
  const openGroup = (group: SampleSet, mode: "edit" | "view" = "view") =>
    setEditorTarget({
      group: { __rowId: group.sample_set_id, ...group },
      mode,
    });

  if (editorTarget) {
    return (
      <SampleGroupEditorPage
        projectId={projectId}
        target={editorTarget}
        onBack={() => setEditorTarget(null)}
        onOpenGroup={openGroup}
      />
    );
  }

  return (
    <DataGridShell
      autoFocusSearch
      columnOptions={SAMPLE_GROUP_COLUMN_OPTIONS}
      columns={columns}
      emptyMessage="No sample groups have been created for this project yet."
      error={queryError(groups.error)}
      hiddenColumns={hiddenColumns}
      isFetching={groups.isFetching}
      isLoading={groups.isLoading}
      itemLabel="groups"
      pageIndex={page}
      pageSize={data?.limit ?? pageSize}
      pageSizeOptions={DATA_PAGE_SIZE_OPTIONS}
      rowKeyGetter={(row) => row.__rowId}
      rows={rows}
      searchPlaceholder="Search sample groups..."
      searchValue={search}
      sortValueGetter={sampleGroupSortValue}
      toolbarActions={
        <Button onClick={() => setEditorTarget({ mode: "new" })} type="button">
          <Plus className="h-4 w-4" /> New group
        </Button>
      }
      total={data?.total ?? 0}
      onHiddenColumnsChange={setHiddenColumns}
      onPageChange={setPage}
      onPageSizeChange={(nextPageSize) => {
        setPageSize(nextPageSize);
        setPage(0);
      }}
      onRowOpen={(group) => openGroup(group)}
      onSearchChange={(value) => {
        setSearch(value);
        setPage(0);
      }}
    />
  );
}

function useSampleColumns(hiddenColumns: Set<string>) {
  return useMemo<Column<SampleGridRow>[]>(() => {
    const columns: Column<SampleGridRow>[] = [
      {
        key: "sample",
        name: "Sample",
        minWidth: 260,
        resizable: true,
        renderCell: ({ row }) => (
          <span className="block w-full truncate text-left font-semibold">
            {row.sample_name ?? row.sample_id}
          </span>
        ),
      },
      {
        key: "subject_id",
        name: "Subject",
        minWidth: 180,
        resizable: true,
        renderCell: ({ row }) => <CellValue value={row.subject_id} />,
      },
      {
        key: "latest_run",
        name: "Latest run",
        minWidth: 240,
        resizable: true,
        renderCell: ({ row }) => (
          <CellValue value={row.latest_run_name ?? row.latest_run_id} />
        ),
      },
      {
        key: "latest_run_created_at",
        name: "Latest activity",
        minWidth: 190,
        resizable: true,
        renderCell: ({ row }) => (
          <CellValue
            value={
              row.latest_run_created_at
                ? formatDate(row.latest_run_created_at)
                : null
            }
          />
        ),
      },
      {
        key: "run_count",
        name: "Runs",
        minWidth: 110,
        resizable: true,
        renderCell: ({ row }) => <NumberCell value={row.run_count} />,
      },
    ];
    return columns.filter((column) => !hiddenColumns.has(column.key));
  }, [hiddenColumns]);
}

function useRunColumns(hiddenColumns: Set<string>) {
  return useMemo<Column<RunGridRow>[]>(() => {
    const columns: Column<RunGridRow>[] = [
      {
        key: "run",
        name: "Run",
        minWidth: 280,
        resizable: true,
        renderCell: ({ row }) => (
          <span className="block w-full truncate text-left font-semibold">
            {row.name ?? row.run_id}
          </span>
        ),
      },
      {
        key: "assay",
        name: "Assay",
        minWidth: 160,
        resizable: true,
        renderCell: ({ row }) => <CellValue value={row.assay} />,
      },
      {
        key: "status",
        name: "Status",
        minWidth: 150,
        resizable: true,
        renderCell: ({ row }) => <CellValue value={row.status} />,
      },
      {
        key: "created_at",
        name: "Created",
        minWidth: 200,
        resizable: true,
        renderCell: ({ row }) => <CellValue value={formatDate(row.created_at)} />,
      },
      {
        key: "samples",
        name: "Samples",
        minWidth: 120,
        resizable: true,
        renderCell: ({ row }) => <NumberCell value={row.samples.length} />,
      },
    ];
    return columns.filter((column) => !hiddenColumns.has(column.key));
  }, [hiddenColumns]);
}

function useSampleGroupColumns(hiddenColumns: Set<string>) {
  return useMemo<Column<SampleGroupGridRow>[]>(() => {
    const columns: Column<SampleGroupGridRow>[] = [
      {
        key: "name",
        name: "Name",
        minWidth: 260,
        resizable: true,
        renderCell: ({ row }) => (
          <span className="block w-full truncate text-left font-semibold">
            {row.name}
          </span>
        ),
      },
      {
        key: "member_count",
        name: "Samples",
        minWidth: 120,
        resizable: true,
        renderCell: ({ row }) => <NumberCell value={row.member_count} />,
      },
      {
        key: "updated_at",
        name: "Updated",
        minWidth: 190,
        resizable: true,
        renderCell: ({ row }) => <CellValue value={formatDate(row.updated_at)} />,
      },
      {
        key: "created_at",
        name: "Created",
        minWidth: 190,
        resizable: true,
        renderCell: ({ row }) => <CellValue value={formatDate(row.created_at)} />,
      },
      {
        key: "description",
        name: "Description",
        minWidth: 320,
        resizable: true,
        renderCell: ({ row }) => <CellValue value={row.description} />,
      },
    ];
    return columns.filter((column) => !hiddenColumns.has(column.key));
  }, [hiddenColumns]);
}

function SampleGroupEditorPage({
  onBack,
  onOpenGroup,
  projectId,
  target,
}: {
  onBack: () => void;
  onOpenGroup: (group: SampleSet, mode?: "edit" | "view") => void;
  projectId: string;
  target: SampleGroupEditorTarget;
}) {
  const group = target.mode === "new" ? null : target.group;
  const groupId = group?.sample_set_id;
  const isReadOnly = target.mode === "view";
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [showDescription, setShowDescription] = useState(false);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState("");
  const [hiddenColumns, setHiddenColumns] = useState<Set<string>>(new Set());
  const [pendingSampleIds, setPendingSampleIds] = useState<Set<string>>(
    new Set(),
  );
  const [selectedRunSamples, setSelectedRunSamples] = useState<Set<string>>(
    new Set(),
  );
  const [addOpen, setAddOpen] = useState(false);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const descriptionRef = useRef<HTMLParagraphElement>(null);
  const [descriptionOverflow, setDescriptionOverflow] = useState(false);
  const offset = page * pageSize;
  const hasDescription = Boolean(description.trim());

  useEffect(() => {
    setName(group?.name ?? "");
    setDescription(group?.description ?? "");
    setShowDescription(false);
    setPage(0);
    setSearch("");
    setPendingSampleIds(new Set());
    setSelectedRunSamples(new Set());
    setActionsOpen(false);
    setConfirmDeleteOpen(false);
  }, [group?.description, group?.name, groupId, target.mode]);

  useEffect(() => {
    if (!isReadOnly || !hasDescription) {
      setDescriptionOverflow(false);
      return;
    }
    const measure = () => {
      const element = descriptionRef.current;
      setDescriptionOverflow(
        Boolean(element && element.scrollWidth > element.clientWidth),
      );
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [description, hasDescription, isReadOnly]);

  const members = useQuery({
    queryKey: [
      "sample-group-members",
      projectId,
      groupId,
      offset,
      pageSize,
      search,
    ],
    queryFn: () =>
      listProjectSampleGroupMembers({
        projectId,
        sampleSetId: groupId ?? "",
        limit: pageSize,
        offset,
        search,
      }),
    enabled: Boolean(groupId),
    placeholderData: (previous) => previous,
  });
  const memberRows = useMemo<SampleGroupMemberGridRow[]>(
    () =>
      (members.data?.items ?? []).map((member) => ({
        __rowId: member.run_sample_id,
        ...member,
      })),
    [members.data?.items],
  );
  const memberColumns = useSampleGroupMemberColumns({
    hiddenColumns,
    selectedRunSamples,
    setSelectedRunSamples,
  });
  const save = useMutation({
    mutationFn: () => {
      const payload = {
        description: description.trim() || null,
        name: name.trim(),
      };
      if (groupId) {
        return patchProjectSampleGroup(projectId, groupId, payload);
      }
      return createProjectSampleGroup(projectId, {
        ...payload,
        sample_ids: Array.from(pendingSampleIds),
      });
    },
    onSuccess: (savedGroup) => {
      void invalidateSampleGroups(projectId, savedGroup.sample_set_id);
      onOpenGroup(savedGroup);
    },
  });
  const remove = useMutation({
    mutationFn: () =>
      removeProjectSampleGroupMembers(
        projectId,
        groupId ?? "",
        Array.from(selectedRunSamples),
      ),
    onSuccess: () => {
      setSelectedRunSamples(new Set());
      void invalidateSampleGroups(projectId, groupId);
    },
  });
  const destroy = useMutation({
    mutationFn: () => deleteProjectSampleGroup(projectId, groupId ?? ""),
    onSuccess: () => {
      setConfirmDeleteOpen(false);
      setActionsOpen(false);
      void invalidateSampleGroups(projectId);
      onBack();
    },
  });
  const error = save.error || remove.error || destroy.error;
  const ActionIcon = groupId ? Save : Plus;
  const handleBack = () => {
    if (target.mode === "edit" && group) {
      onOpenGroup(group);
      return;
    }
    onBack();
  };
  const descriptionButton = (
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
  );
  const saveButton = (
    <Button
      disabled={save.isPending || !name.trim()}
      type="button"
      onClick={() => save.mutate()}
    >
      <ActionIcon className="h-4 w-4" /> {groupId ? "Save" : "Create"}
    </Button>
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-white">
      <section className="shrink-0 border-b border-[#dce3eb] px-4 py-3">
        <div className="flex items-center gap-3">
          <Button
            aria-label="Back to sample groups"
            size="icon"
            type="button"
            variant="ghost"
            onClick={handleBack}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <Users className="h-5 w-5 shrink-0 text-[#16784a]" />
          {isReadOnly && group ? (
            <>
              <div className="min-w-0 flex-1">
                <h2 className="truncate text-lg font-semibold text-[#1f2937]">
                  {group.name}
                </h2>
                {hasDescription ? (
                  <div className="mt-0.5 flex min-w-0 items-center gap-1.5">
                    <p
                      className="min-w-0 truncate text-xs text-[#657082]"
                      ref={descriptionRef}
                    >
                      {description}
                    </p>
                    {descriptionOverflow ? (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            aria-label="Show full description"
                            className="h-6 w-6 shrink-0 text-[#657082] hover:text-[#1f2937]"
                            size="icon"
                            type="button"
                            variant="ghost"
                          >
                            <Plus className="h-3.5 w-3.5" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent
                          align="start"
                          className="max-w-[420px] p-3 text-sm leading-6 text-[#253044]"
                        >
                          {description}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <DropdownMenu
                open={actionsOpen}
                onOpenChange={(open) => {
                  setActionsOpen(open);
                  if (!open) setConfirmDeleteOpen(false);
                }}
              >
                <DropdownMenuTrigger asChild>
                  <Button
                    aria-label="Sample group actions"
                    size="icon"
                    type="button"
                    variant="ghost"
                  >
                    <MoreVertical className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="end"
                  className={confirmDeleteOpen ? "w-[280px] p-3" : "min-w-[180px]"}
                >
                  {confirmDeleteOpen ? (
                    <div className="space-y-3">
                      <div>
                        <div className="text-sm font-semibold text-[#1f2937]">
                          Delete sample group?
                        </div>
                        <p className="mt-1 text-xs leading-5 text-[#657082]">
                          This will delete "{group.name}". The samples
                          themselves will remain in the project.
                        </p>
                      </div>
                      <div className="flex justify-end gap-2">
                        <Button
                          disabled={destroy.isPending}
                          size="sm"
                          type="button"
                          variant="outline"
                          onClick={() => setConfirmDeleteOpen(false)}
                        >
                          Cancel
                        </Button>
                        <Button
                          className="bg-[#b42318] text-white hover:bg-[#912018]"
                          disabled={destroy.isPending}
                          size="sm"
                          type="button"
                          onClick={() => destroy.mutate()}
                        >
                          Delete
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <DropdownMenuItem
                        onSelect={() => onOpenGroup(group, "edit")}
                      >
                        <Pencil className="h-4 w-4" /> Edit
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        className="text-[#b42318] focus:bg-[#fff1f0]"
                        onSelect={(event) => {
                          event.preventDefault();
                          setConfirmDeleteOpen(true);
                        }}
                      >
                        <Trash2 className="h-4 w-4" /> Delete
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          ) : (
            <>
              <Input
                autoFocus
                className="h-10 flex-1 text-lg font-semibold"
                placeholder="Sample group name"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
              {descriptionButton}
              {saveButton}
            </>
          )}
        </div>
        {!isReadOnly && showDescription ? (
          <div className="mt-3 flex items-start gap-2">
            <textarea
              className="h-10 min-h-10 flex-1 resize-y rounded-md border border-[#d6dee8] bg-white px-3 py-2 text-sm text-[#1f2937] outline-none transition-colors placeholder:text-[#9ca3af] focus:border-[#16784a] focus:ring-2 focus:ring-[#16784a]/15"
              placeholder="Enter description (optional)"
              rows={1}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
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
        {error ? (
          <p className="mt-2 text-sm text-[#b42318]">
            {queryError(error)?.message}
          </p>
        ) : null}
      </section>
      {groupId ? (
        <div className="min-h-0 flex-1 overflow-hidden p-4">
          <div className="h-full min-h-0 overflow-hidden rounded-lg border border-[#dce3eb]">
            <DataGridShell
              columnOptions={SAMPLE_GROUP_MEMBER_COLUMN_OPTIONS}
              columns={memberColumns}
              emptyMessage="This group does not have any samples yet."
              error={queryError(members.error)}
              hiddenColumns={hiddenColumns}
              isFetching={members.isFetching}
              isLoading={members.isLoading}
              itemLabel="members"
              pageIndex={page}
              pageSize={members.data?.limit ?? pageSize}
              pageSizeOptions={PICKER_PAGE_SIZE_OPTIONS}
              rowKeyGetter={(row) => row.__rowId}
              rows={memberRows}
              searchPlaceholder="Search group samples..."
              searchValue={search}
              selectionFirstColumn
              sortValueGetter={sampleGroupMemberSortValue}
              toolbarActions={
                <>
                  <Button type="button" onClick={() => setAddOpen(true)}>
                    <Plus className="h-4 w-4" /> Add
                  </Button>
                  {selectedRunSamples.size > 0 ? (
                    <Button
                      className="bg-[#b42318] text-white hover:bg-[#912018]"
                      disabled={remove.isPending}
                      type="button"
                      onClick={() => remove.mutate()}
                    >
                      Remove
                    </Button>
                  ) : null}
                </>
              }
              total={members.data?.total ?? 0}
              onHiddenColumnsChange={setHiddenColumns}
              onPageChange={setPage}
              onPageSizeChange={(nextPageSize) => {
                setPageSize(nextPageSize);
                setPage(0);
              }}
              onSearchChange={(value) => {
                setSearch(value);
                setPage(0);
              }}
            />
          </div>
          <AddSamplesDialog
            open={addOpen}
            projectId={projectId}
            sampleSetId={groupId}
            onOpenChange={setAddOpen}
          />
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-hidden p-4">
          <div className="h-full min-h-0 overflow-hidden rounded-lg border border-[#dce3eb]">
            <SamplePickerGrid
              projectId={projectId}
              selectedSamples={pendingSampleIds}
              setSelectedSamples={setPendingSampleIds}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function useSampleGroupMemberColumns({
  hiddenColumns,
  selectedRunSamples,
  setSelectedRunSamples,
}: {
  hiddenColumns: Set<string>;
  selectedRunSamples: Set<string>;
  setSelectedRunSamples: (value: Set<string>) => void;
}) {
  return useMemo<Column<SampleGroupMemberGridRow>[]>(() => {
    const columns: Column<SampleGroupMemberGridRow>[] = [
      {
        key: "selected",
        name: "",
        sortable: false,
        width: 48,
        minWidth: 48,
        frozen: true,
        renderCell: ({ row }) => (
          <input
            aria-label={`Select ${row.sample_id}`}
            checked={selectedRunSamples.has(row.run_sample_id)}
            type="checkbox"
            onChange={(event) => {
              const next = new Set(selectedRunSamples);
              if (event.target.checked) next.add(row.run_sample_id);
              else next.delete(row.run_sample_id);
              setSelectedRunSamples(next);
            }}
            onClick={(event) => event.stopPropagation()}
          />
        ),
      },
      {
        key: "sample",
        name: "Sample",
        minWidth: 220,
        resizable: true,
        renderCell: ({ row }) => (
          <span className="block w-full truncate text-left font-semibold">
            {row.sample_name ?? row.sample_id}
          </span>
        ),
      },
      {
        key: "subject_id",
        name: "Subject",
        minWidth: 180,
        resizable: true,
        renderCell: ({ row }) => <CellValue value={row.subject_id} />,
      },
      {
        key: "run",
        name: "Run",
        minWidth: 220,
        resizable: true,
        renderCell: ({ row }) => <CellValue value={row.run_name ?? row.run_id} />,
      },
      {
        key: "status",
        name: "Status",
        minWidth: 140,
        resizable: true,
        renderCell: ({ row }) => <CellValue value={row.status} />,
      },
    ];
    return columns.filter(
      (column) => column.key === "selected" || !hiddenColumns.has(column.key),
    );
  }, [hiddenColumns, selectedRunSamples, setSelectedRunSamples]);
}

function AddSamplesDialog({
  onOpenChange,
  open,
  projectId,
  sampleSetId,
}: {
  onOpenChange: (open: boolean) => void;
  open: boolean;
  projectId: string;
  sampleSetId: string;
}) {
  const [selectedSamples, setSelectedSamples] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!open) return;
    setSelectedSamples(new Set());
  }, [open]);

  const add = useMutation({
    mutationFn: () =>
      addProjectSampleGroupMembers(
        projectId,
        sampleSetId,
        Array.from(selectedSamples),
      ),
    onSuccess: () => {
      setSelectedSamples(new Set());
      onOpenChange(false);
      void invalidateSampleGroups(projectId, sampleSetId);
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] max-w-[840px] overflow-hidden">
        <DialogHeader className="border-b border-[#dce3eb] pb-4">
          <DialogTitle>Add</DialogTitle>
        </DialogHeader>
        <div className="h-[470px] min-h-0 overflow-hidden rounded-lg border border-[#dce3eb]">
          <SamplePickerGrid
            enabled={open}
            projectId={projectId}
            queryKeySuffix={sampleSetId}
            selectedSamples={selectedSamples}
            setSelectedSamples={setSelectedSamples}
          />
        </div>
        {add.error ? (
          <p className="m-0 text-sm text-[#b42318]">
            {queryError(add.error)?.message}
          </p>
        ) : null}
        <DialogFooter>
          <Button
            disabled={add.isPending}
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            disabled={selectedSamples.size === 0 || add.isPending}
            type="button"
            onClick={() => add.mutate()}
          >
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SamplePickerGrid({
  enabled = true,
  projectId,
  queryKeySuffix = "create",
  selectedSamples,
  setSelectedSamples,
}: {
  enabled?: boolean;
  projectId: string;
  queryKeySuffix?: string;
  selectedSamples: Set<string>;
  setSelectedSamples: (value: Set<string>) => void;
}) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState("");
  const offset = page * pageSize;
  const samples = useQuery({
    queryKey: [
      "sample-group-sample-picker",
      projectId,
      queryKeySuffix,
      offset,
      pageSize,
      search,
    ],
    queryFn: () =>
      listProjectSamples({ projectId, limit: pageSize, offset, search }),
    enabled,
    placeholderData: (previous) => previous,
  });
  const rows = useMemo<SampleGridRow[]>(
    () =>
      (samples.data?.items ?? []).map((sample) => ({
        __rowId: sample.sample_id,
        ...sample,
      })),
    [samples.data?.items],
  );
  const columns = useAddSampleColumns({ selectedSamples, setSelectedSamples });
  const toggleSample = useCallback(
    (sampleId: string) => {
      const next = new Set(selectedSamples);
      if (next.has(sampleId)) next.delete(sampleId);
      else next.add(sampleId);
      setSelectedSamples(next);
    },
    [selectedSamples, setSelectedSamples],
  );

  return (
    <DataGridShell
      columns={columns}
      emptyMessage="No samples match this search."
      error={queryError(samples.error)}
      isFetching={samples.isFetching}
      isLoading={samples.isLoading}
      itemLabel="samples"
      pageIndex={page}
      pageSize={samples.data?.limit ?? pageSize}
      pageSizeOptions={PICKER_PAGE_SIZE_OPTIONS}
      rowKeyGetter={(row) => row.__rowId}
      rows={rows}
      searchPlaceholder="Search samples..."
      searchValue={search}
      selectionFirstColumn
      sortValueGetter={sampleSortValue}
      total={samples.data?.total ?? 0}
      onPageChange={setPage}
      onPageSizeChange={(nextPageSize) => {
        setPageSize(nextPageSize);
        setPage(0);
      }}
      onSearchChange={(value) => {
        setSearch(value);
        setPage(0);
      }}
      onRowOpen={(row) => toggleSample(row.sample_id)}
    />
  );
}

function useAddSampleColumns({
  selectedSamples,
  setSelectedSamples,
}: {
  selectedSamples: Set<string>;
  setSelectedSamples: (value: Set<string>) => void;
}) {
  return useMemo<Column<SampleGridRow>[]>(() => {
    return [
      {
        key: "selected",
        name: "",
        sortable: false,
        width: 48,
        minWidth: 48,
        frozen: true,
        renderCell: ({ row }) => (
          <input
            aria-label={`Select ${row.sample_id}`}
            checked={selectedSamples.has(row.sample_id)}
            type="checkbox"
            onChange={(event) => {
              const next = new Set(selectedSamples);
              if (event.target.checked) next.add(row.sample_id);
              else next.delete(row.sample_id);
              setSelectedSamples(next);
            }}
            onClick={(event) => event.stopPropagation()}
          />
        ),
      },
      {
        key: "sample",
        name: "Sample",
        minWidth: 240,
        resizable: true,
        renderCell: ({ row }) => (
          <span className="block w-full truncate text-left font-semibold">
            {row.sample_name ?? row.sample_id}
          </span>
        ),
      },
      {
        key: "subject_id",
        name: "Subject",
        minWidth: 170,
        resizable: true,
        renderCell: ({ row }) => <CellValue value={row.subject_id} />,
      },
      {
        key: "latest_run",
        name: "Latest run",
        minWidth: 220,
        resizable: true,
        renderCell: ({ row }) => (
          <CellValue value={row.latest_run_name ?? row.latest_run_id} />
        ),
      },
    ];
  }, [selectedSamples, setSelectedSamples]);
}

function sampleSortValue(row: SampleGridRow, columnKey: string) {
  switch (columnKey) {
    case "sample":
      return row.sample_name ?? row.sample_id;
    case "latest_run":
      return row.latest_run_name ?? row.latest_run_id;
    default:
      return row[columnKey as keyof SampleGridRow];
  }
}

function runSortValue(row: RunGridRow, columnKey: string) {
  switch (columnKey) {
    case "run":
      return row.name ?? row.run_id;
    case "samples":
      return row.samples.length;
    default:
      return row[columnKey as keyof RunGridRow];
  }
}

function sampleGroupSortValue(row: SampleGroupGridRow, columnKey: string) {
  return row[columnKey as keyof SampleGroupGridRow];
}

function sampleGroupMemberSortValue(
  row: SampleGroupMemberGridRow,
  columnKey: string,
) {
  switch (columnKey) {
    case "sample":
      return row.sample_name ?? row.sample_id;
    case "run":
      return row.run_name ?? row.run_id;
    default:
      return row[columnKey as keyof SampleGroupMemberGridRow];
  }
}

function CellValue({ value }: { value?: string | null }) {
  return (
    <span className="block w-full truncate text-left text-[#253044]">
      {value || "—"}
    </span>
  );
}

function NumberCell({ value }: { value: number }) {
  return (
    <span className="block w-full truncate text-left text-[#253044]">
      {value.toLocaleString()}
    </span>
  );
}

function queryError(error: unknown): Error | null {
  return error instanceof Error ? error : null;
}

async function invalidateSampleGroups(projectId: string, sampleSetId?: string) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: ["sample-groups", projectId] }),
    queryClient.invalidateQueries({ queryKey: ["sample-sets", projectId] }),
    sampleSetId
      ? queryClient.invalidateQueries({
          queryKey: ["sample-group-members", projectId, sampleSetId],
        })
      : Promise.resolve(),
  ]);
}
