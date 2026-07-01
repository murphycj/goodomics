import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useRouterState } from "@tanstack/react-router";
import {
  BarChart3,
  Database,
  FileText,
  FlaskConical,
  Gauge,
  Home,
  Layers3,
  Settings as SettingsIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { getProject, listReports, patchProject } from "../../api";
import { queryClient } from "../../lib/queryClient";
import type { SidebarMode } from "../../lib/types";
import { cn } from "../../lib/utils";
import {
  Button,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui";
import { SidebarModeSelect } from "./SidebarModeSelect";

const navItems = [
  { suffix: "/samples", label: "Samples", icon: FlaskConical },
  { suffix: "/runs", label: "Runs", icon: Gauge },
  { suffix: "/reports", label: "Reports", icon: FileText },
  { suffix: "/insights", label: "Insights", icon: BarChart3 },
  { suffix: "/cohorts", label: "Cohorts", icon: Layers3 },
  { suffix: "/qc-policies", label: "QC policies", icon: Gauge },
  { suffix: "/database", label: "Database", icon: Database },
  { suffix: "/settings", label: "Settings", icon: SettingsIcon },
] as const;

const NO_DEFAULT_REPORT = "__default_home__";

/** Project navigation sidebar with collapsible and hover-expand modes. */
export function Sidebar({
  mode,
  onModeChange,
  projectId,
}: {
  mode: SidebarMode;
  onModeChange: (mode: SidebarMode) => void;
  projectId: string;
}) {
  const [controlOpen, setControlOpen] = useState(false);
  const [homeSettingsOpen, setHomeSettingsOpen] = useState(false);
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const isExpanded = mode === "expanded";
  const shouldHoldHoverOpen = mode === "hover" && (controlOpen || homeSettingsOpen);
  const isVisuallyExpanded = isExpanded || shouldHoldHoverOpen;

  return (
    <aside
      className={cn(
        "fixed bottom-0 left-0 top-12 z-20 hidden flex-col justify-between overflow-visible border-r border-[#2a2a2a] bg-[#151515] p-[0.65rem_0.45rem] text-[#f6f6f6] transition-[width] duration-[170ms] md:flex",
        isVisuallyExpanded ? "w-[232px]" : "w-[58px]",
        mode === "hover" &&
          !shouldHoldHoverOpen &&
          "group/sidebar hover:w-[232px]",
      )}
    >
      <nav className="grid gap-1">
        <HomeNavItem
          expanded={isVisuallyExpanded}
          mode={mode}
          pathname={pathname}
          projectId={projectId}
          settingsOpen={homeSettingsOpen}
          onSettingsOpenChange={setHomeSettingsOpen}
        />
        {navItems.map(({ suffix, label, icon: Icon }) => {
          const to = `/project/${projectId}${suffix}`;
          return (
            <Link
              activeProps={{ className: "!bg-[#2b2b2b] !text-white" }}
              className="flex h-[38px] w-full min-w-0 cursor-pointer items-center gap-3 rounded-[7px] border-0 bg-transparent px-[0.72rem] text-[#b7bdc5] no-underline transition-colors hover:bg-[#2b2b2b] hover:text-white"
              key={label}
              title={label}
              to={to}
            >
              <Icon className="h-[18px] w-[18px] shrink-0" />
              <span
                className={cn(
                  "max-w-0 overflow-hidden text-ellipsis whitespace-nowrap opacity-0 transition-[opacity,max-width] duration-[170ms]",
                  isVisuallyExpanded && "max-w-[150px] opacity-100",
                  mode === "hover" &&
                    !shouldHoldHoverOpen &&
                    "group-hover/sidebar:max-w-[150px] group-hover/sidebar:opacity-100",
                )}
              >
                {label}
              </span>
            </Link>
          );
        })}
      </nav>
      <SidebarModeSelect
        expanded={isVisuallyExpanded}
        hoverModeHeldOpen={shouldHoldHoverOpen}
        mode={mode}
        onModeChange={onModeChange}
        onOpenChange={setControlOpen}
      />
    </aside>
  );
}

/** Home navigation row with inline access to default homepage settings. */
function HomeNavItem({
  expanded,
  mode,
  onSettingsOpenChange,
  pathname,
  projectId,
  settingsOpen,
}: {
  expanded: boolean;
  mode: SidebarMode;
  onSettingsOpenChange: (open: boolean) => void;
  pathname: string;
  projectId: string;
  settingsOpen: boolean;
}) {
  const isActive = pathname === `/project/${projectId}`;
  return (
    <div
      className={cn(
        "flex h-[38px] w-full min-w-0 items-center rounded-[7px] transition-colors hover:bg-[#2b2b2b]",
        isActive && "bg-[#2b2b2b] text-white",
      )}
    >
      <Link
        className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 px-[0.72rem] text-[#b7bdc5] no-underline transition-colors hover:text-white"
        params={{ projectId }}
        to="/project/$projectId"
        title="Home"
      >
        <Home className="h-[18px] w-[18px] shrink-0" />
        <span
          className={cn(
            "max-w-0 overflow-hidden text-ellipsis whitespace-nowrap opacity-0 transition-[opacity,max-width] duration-[170ms]",
            expanded && "max-w-[108px] opacity-100",
            mode === "hover" &&
              "group-hover/sidebar:max-w-[108px] group-hover/sidebar:opacity-100",
          )}
        >
          Home
        </span>
      </Link>
      <button
        aria-label="Configure project homepage"
        className={cn(
          "mr-1 hidden h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md border-0 bg-transparent text-[#8f98a6] transition hover:bg-[#383838] hover:text-white",
          expanded && "inline-flex",
          mode === "hover" && "group-hover/sidebar:inline-flex",
        )}
        onClick={() => onSettingsOpenChange(true)}
        type="button"
      >
        <SettingsIcon className="h-4 w-4" />
      </button>
      <ProjectHomeSettingsDialog
        open={settingsOpen}
        projectId={projectId}
        onOpenChange={onSettingsOpenChange}
      />
    </div>
  );
}

/** Dialog for choosing whether project home opens the default page or a report. */
function ProjectHomeSettingsDialog({
  onOpenChange,
  open,
  projectId,
}: {
  onOpenChange: (open: boolean) => void;
  open: boolean;
  projectId: string;
}) {
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
    enabled: open,
  });
  const reports = useQuery({
    queryKey: ["reports", projectId],
    queryFn: () => listReports(projectId),
    enabled: open,
  });
  const defaultReport = useMutation({
    mutationFn: (reportId: string | null) =>
      patchProject(projectId, { default_report_id: reportId }),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
  });
  const [selectedMode, setSelectedMode] = useState<"default" | "report" | null>(null);
  const selectedReportId = project.data?.default_report_id ?? NO_DEFAULT_REPORT;
  const homeMode =
    selectedMode ?? (project.data?.default_report_id ? "report" : "default");

  useEffect(() => {
    if (!open) {
      setSelectedMode(null);
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[760px]">
        <DialogHeader className="border-b border-[#dce3eb] pb-4">
          <DialogTitle>Configure homepage</DialogTitle>
          <p className="m-0 text-sm text-[#657082]">
            Choose the default landing view for this project.
          </p>
        </DialogHeader>
        <div className="grid gap-5">
          <div className="rounded-lg border border-[#dce3eb] bg-[#f8fafb] p-3">
            <div className="mb-3 flex items-center gap-3">
              <Home className="h-5 w-5 text-[#657082]" />
              <div>
                <div className="text-sm font-semibold text-[#1d2430]">Home</div>
                <div className="text-xs text-[#657082]">Project launchpad</div>
              </div>
            </div>
            <div className="inline-flex rounded-lg border border-[#cfd8e3] bg-white p-1">
              <Button
                variant={homeMode === "default" ? "default" : "ghost"}
                onClick={() => {
                  setSelectedMode("default");
                  defaultReport.mutate(null);
                }}
              >
                Default
              </Button>
              <Button
                variant={homeMode === "report" ? "default" : "ghost"}
                onClick={() => {
                  setSelectedMode("report");
                  const firstReport = reports.data?.[0];
                  if (firstReport && !project.data?.default_report_id) {
                    defaultReport.mutate(firstReport.report_id);
                  }
                }}
              >
                Report
              </Button>
            </div>
          </div>
          {homeMode === "report" ? (
            <div className="space-y-1.5 rounded-lg border border-[#dce3eb] bg-white p-4">
              <Label>Default report</Label>
              <Select
                value={selectedReportId}
                onValueChange={(value) =>
                  defaultReport.mutate(value === NO_DEFAULT_REPORT ? null : value)
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Choose report" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_DEFAULT_REPORT}>
                    No default report / show home
                  </SelectItem>
                  {(reports.data ?? []).map((report) => (
                    <SelectItem key={report.report_id} value={report.report_id}>
                      {report.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
