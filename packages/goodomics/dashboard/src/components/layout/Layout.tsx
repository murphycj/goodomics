import { useQuery } from "@tanstack/react-query";
import { Outlet, useRouterState } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { getProject, listProjects } from "../../api";
import type { SidebarMode } from "../../lib/types";
import { cn, projectIdFromPath } from "../../lib/utils";
import { SearchOverlay } from "../search/SearchOverlay";
import { AppHeader } from "./AppHeader";
import { Sidebar } from "./Sidebar";

export function Layout() {
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  });
  const projectId = projectIdFromPath(pathname);
  const [searchOpen, setSearchOpen] = useState(false);
  const [sidebarMode, setSidebarMode] = useState<SidebarMode>("hover");
  const projects = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const selectedProject = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId ?? ""),
    enabled: Boolean(projectId),
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <main className="min-h-screen bg-[#f7f8fa]">
      <AppHeader
        onOpenSearch={() => setSearchOpen(true)}
        project={selectedProject.data}
        projects={projects.data ?? []}
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
          "px-4 pb-8 pt-[72px] md:px-8",
          projectId && "transition-[margin-left] duration-[170ms] md:ml-[58px]",
          projectId && sidebarMode === "expanded" && "md:ml-[232px]",
          !projectId && "mx-auto max-w-[1160px]",
        )}
      >
        <Outlet />
      </section>
      <SearchOverlay
        onClose={() => setSearchOpen(false)}
        open={searchOpen}
        projectId={projectId ?? undefined}
      />
    </main>
  );
}
