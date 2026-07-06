import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import {
  BarChart3,
  Clock3,
  Database,
  FileText,
  FlaskConical,
  PlayCircle,
  Search,
  Star,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  getProject,
  listInsights,
  listReports,
  type SavedInsight,
  type SavedReport,
} from "../api";
import { useSearch } from "../components/search/SearchProvider";
import { Card, CardContent } from "../components/ui";
import {
  readProjectRecentViews,
  type ProjectRecentKind,
  type ProjectRecentView,
} from "../lib/projectRecents";

type HomeView = {
  description: string;
  href: string;
  icon: typeof FileText;
  timestamp: string | null;
  title: string;
};

/** Project launchpad with focused search, recent views, starred views, and core counts. */
export function ProjectHomePage({ projectId }: { projectId: string }) {
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
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [draft, setDraft] = useState("");
  const [storedRecentViews, setStoredRecentViews] = useState<
    ProjectRecentView[]
  >([]);
  const { openSearch } = useSearch();
  const navigate = useNavigate();

  useEffect(() => {
    inputRef.current?.focus();
    setStoredRecentViews(readProjectRecentViews(projectId));
  }, [projectId]);

  const recentViews = useMemo(
    () =>
      buildRecentViews({
        insights: insights.data ?? [],
        projectId,
        reports: reports.data ?? [],
        storedViews: storedRecentViews,
        latestActivityAt: project.data?.latest_activity_at ?? null,
      }),
    [
      insights.data,
      project.data?.latest_activity_at,
      projectId,
      reports.data,
      storedRecentViews,
    ],
  );

  const openHref = (href: string) => {
    window.location.href = href;
  };

  return (
    <div className="mx-auto flex min-h-[calc(100vh-96px)] max-w-[980px] flex-col justify-center gap-9 py-10">
      <section className="text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg border border-[#dce3eb] bg-white text-[#16784a] shadow-[0_14px_34px_rgb(25_32_43/0.06)]">
          <Database className="h-6 w-6" />
        </div>
        <h1 className="m-0 text-3xl font-semibold tracking-normal text-[#1d2430]">
          {project.data?.name ?? "Project home"}
        </h1>
        <div className="relative mx-auto mt-6 max-w-[720px]">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#758195]" />
          <input
            ref={inputRef}
            className="h-14 w-full rounded-xl border border-[#cfd8e3] bg-white px-12 text-base text-[#1d2430] shadow-[0_16px_42px_rgb(25_32_43/0.08)] outline-none transition focus:border-[#8edeb4] focus:ring-2 focus:ring-[#21a66a]/25"
            placeholder="Search samples and runs in this project..."
            value={draft}
            onChange={(event) => {
              const nextDraft = event.target.value;
              setDraft(nextDraft);
              openSearch(nextDraft);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") openSearch(draft);
            }}
          />
          <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-sm text-[#758195]">
            Enter to search
          </span>
        </div>
      </section>

      <section className="mx-auto grid w-full max-w-[660px] gap-5 md:grid-cols-2">
        <ViewColumn
          empty="No recent project views yet."
          icon={Clock3}
          title="Recent views"
          views={recentViews}
          onOpen={openHref}
        />
        <ViewColumn
          empty="Starred views will appear here."
          icon={Star}
          title="Starred views"
          views={[]}
          onOpen={openHref}
        />
      </section>

      <section className="grid gap-3 md:grid-cols-3">
        <StatCard
          icon={FlaskConical}
          label="Samples"
          value={project.data?.sample_count ?? 0}
          onClick={() =>
            void navigate({
              to: "/project/$projectId/samples",
              params: { projectId },
            })
          }
        />
        <StatCard
          icon={PlayCircle}
          label="Runs"
          value={project.data?.run_count ?? 0}
          onClick={() =>
            void navigate({
              to: "/project/$projectId/runs",
              params: { projectId },
            })
          }
        />
        <StatCard
          icon={Users}
          label="Subjects"
          value={project.data?.subject_count ?? 0}
          onClick={() => {
            window.location.href = `/project/${encodeURIComponent(
              projectId,
            )}/database?store=catalog&table=subjects`;
          }}
        />
      </section>
    </div>
  );
}

/** Compact list column used for recent and starred project views. */
function ViewColumn({
  empty,
  icon: Icon,
  onOpen,
  title,
  views,
}: {
  empty: string;
  icon: typeof Clock3;
  onOpen: (href: string) => void;
  title: string;
  views: HomeView[];
}) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-1.5 text-[0.68rem] font-bold uppercase tracking-[0.08em] text-[#657082]">
        <Icon className="h-3.5 w-3.5" />
        {title}
      </div>
      <div className="grid gap-1">
        {views.length === 0 ? (
          <div className="rounded-md border border-dashed border-[#cfd8e3] bg-white/70 px-3 py-2 text-xs text-[#657082]">
            {empty}
          </div>
        ) : (
          views.map((view) => {
            const ViewIcon = view.icon;
            return (
              <button
                className="flex min-h-[40px] cursor-pointer items-center gap-2 rounded-md border border-transparent bg-transparent px-2 py-1 text-left transition hover:border-[#dce3eb] hover:bg-white"
                key={`${view.href}:${view.title}`}
                onClick={() => onOpen(view.href)}
                type="button"
              >
                <ViewIcon className="h-3.5 w-3.5 shrink-0 text-[#16784a]" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-semibold text-[#1d2430]">
                    {view.title}
                  </span>
                  <span className="block truncate text-[0.68rem] text-[#657082]">
                    {view.description}
                  </span>
                </span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

/** Clickable project statistic tile that routes to the related project view. */
function StatCard({
  icon: Icon,
  label,
  onClick,
  value,
}: {
  icon: typeof FlaskConical;
  label: string;
  onClick: () => void;
  value: number;
}) {
  return (
    <Card className="mt-0 p-0">
      <CardContent className="p-0">
        <button
          className="flex h-full min-h-[118px] w-full cursor-pointer items-center gap-4 rounded-lg border-0 bg-transparent p-4 text-left transition hover:bg-[#eef8f2]"
          onClick={onClick}
          type="button"
        >
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-[#e8f7ee] text-[#16784a]">
            <Icon className="h-5 w-5" />
          </span>
          <span>
            <span className="block text-3xl font-semibold tracking-normal text-[#1d2430]">
              {value.toLocaleString()}
            </span>
            <span className="mt-1 block text-sm text-[#657082]">{label}</span>
          </span>
        </button>
      </CardContent>
    </Card>
  );
}

function buildRecentViews({
  insights,
  latestActivityAt,
  projectId,
  reports,
  storedViews,
}: {
  insights: SavedInsight[];
  latestActivityAt: string | null;
  projectId: string;
  reports: SavedReport[];
  storedViews: ProjectRecentView[];
}): HomeView[] {
  const stored = storedViews.map((view) => ({
    description: view.description,
    href: view.href,
    icon: iconForRecentKind(view.kind),
    timestamp: view.timestamp,
    title: view.title,
  }));
  const baseViews: HomeView[] = [
    {
      description: "Sample table",
      href: `/project/${projectId}/samples`,
      icon: FlaskConical,
      timestamp: latestActivityAt,
      title: "Samples",
    },
    {
      description: "Run history",
      href: `/project/${projectId}/runs`,
      icon: PlayCircle,
      timestamp: latestActivityAt,
      title: "Runs",
    },
  ];
  const reportViews = reports.slice(0, 3).map((report) => ({
    description: "Report",
    href: `/project/${projectId}/reports`,
    icon: FileText,
    timestamp: report.updated_at,
    title: report.name,
  }));
  const insightViews = insights.slice(0, 3).map((insight) => ({
    description: "Insight",
    href: `/project/${projectId}/insights?insight=${encodeURIComponent(
      insight.insight_id,
    )}`,
    icon: BarChart3,
    timestamp: insight.updated_at,
    title: insight.name,
  }));
  return [...stored, ...baseViews, ...reportViews, ...insightViews]
    .filter(
      (view, index, allViews) =>
        allViews.findIndex((candidate) => candidate.href === view.href) ===
        index,
    )
    .sort(
      (left, right) => dateScore(right.timestamp) - dateScore(left.timestamp),
    )
    .slice(0, 5);
}

function dateScore(value: string | null) {
  return value ? new Date(value).getTime() : 0;
}

function iconForRecentKind(kind: ProjectRecentKind) {
  return {
    database: Database,
    insight: BarChart3,
    policies: FileText,
    report: FileText,
    run: PlayCircle,
    runs: PlayCircle,
    sample: FlaskConical,
    "sample-groups": Users,
    samples: FlaskConical,
    settings: Database,
  }[kind];
}
