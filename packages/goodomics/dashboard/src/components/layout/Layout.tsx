import { useQuery } from "@tanstack/react-query";
import { Outlet, useRouterState } from "@tanstack/react-router";
import type { CSSProperties } from "react";
import { useEffect, useState } from "react";
import { getProject, listProjects } from "../../api";
import { recordProjectRecentView } from "../../lib/projectRecents";
import type { SidebarMode } from "../../lib/types";
import { cn, projectIdFromPath } from "../../lib/utils";
import { SearchProvider, useSearch } from "../search/SearchProvider";
import { useSearchStore } from "../search/searchStore";
import { Toaster } from "../ui/sonner";
import { AppHeader } from "./AppHeader";
import { Sidebar } from "./Sidebar";

/** Root dashboard shell that wires project context into search and navigation. */
export function Layout() {
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  });
  const projectId = projectIdFromPath(pathname);
  const [sidebarMode, setSidebarMode] = useState<SidebarMode>("hover");
  const projects = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const selectedProject = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId ?? ""),
    enabled: Boolean(projectId),
  });

  return (
    <SearchProvider
      defaultProjectId={projectId ?? undefined}
      defaultProjectName={selectedProject.data?.name}
    >
      <LayoutContent
        pathname={pathname}
        projectId={projectId}
        projects={projects.data ?? []}
        selectedProject={selectedProject.data}
        sidebarMode={sidebarMode}
        setSidebarMode={setSidebarMode}
      />
    </SearchProvider>
  );
}

/** Main application frame with header, sidebar, routed content, and recents tracking. */
function LayoutContent({
  pathname,
  projectId,
  projects,
  selectedProject,
  setSidebarMode,
  sidebarMode,
}: {
  pathname: string;
  projectId: string | null;
  projects: Awaited<ReturnType<typeof listProjects>>;
  selectedProject?: Awaited<ReturnType<typeof getProject>>;
  setSidebarMode: (mode: SidebarMode) => void;
  sidebarMode: SidebarMode;
}) {
  const { openSearch } = useSearch();
  const askOpen = useSearchStore((state) => state.askOpen);
  const askWidth = useSearchStore((state) => state.askWidth);
  const askInset = askOpen ? askWidth : 0;
  const isTableCanvas =
    pathname === `/project/${projectId}/samples` ||
    pathname === `/project/${projectId}/sample-groups` ||
    pathname === `/project/${projectId}/runs` ||
    pathname === `/project/${projectId}/database`;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openSearch();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [openSearch]);

  useEffect(() => {
    if (!projectId) return;
    recordProjectRecentView(projectId, pathname);
  }, [pathname, projectId]);

  return (
    <main
      className="min-h-screen bg-[#f7f8fa] transition-[margin-right] duration-200 ease-out md:mr-[var(--ask-ai-inset)]"
      style={{ "--ask-ai-inset": `${askInset}px` } as CSSProperties}
    >
      <AppHeader
        askInset={askInset}
        project={selectedProject}
        projects={projects}
      />
      {projectId && (
        <Sidebar
          mode={sidebarMode}
          onModeChange={setSidebarMode}
          projectId={projectId}
        />
      )}
      <section
        className={cn(
          "transition-[margin-left] duration-[170ms]",
          isTableCanvas ? "px-0 pt-[48px]" : "px-4 pb-8 pt-[72px] md:px-8",
          projectId && "md:ml-[58px]",
          projectId && sidebarMode === "expanded" && "md:ml-[232px]",
          !projectId && "mx-auto max-w-[1160px]",
        )}
      >
        <Outlet />
      </section>
      <Toaster />
    </main>
  );
}
