import { Link } from "@tanstack/react-router";
import { Activity, Search } from "lucide-react";
import type { GoodomicsProject } from "../../api";
import { useSearch } from "../search/SearchProvider";
import { ProjectSwitcherMenu } from "./ProjectSwitcherMenu";

export function AppHeader({
  project,
  projects,
}: {
  project?: GoodomicsProject;
  projects: GoodomicsProject[];
}) {
  const { openSearch } = useSearch();

  return (
    <header className="fixed left-0 right-0 top-0 z-30 flex h-12 items-center justify-between gap-4 border-b border-[#2a2a2a] bg-[#111111] px-4 text-[#f6f6f6]">
      <div className="flex min-w-0 items-center gap-3">
        <Link
          className="inline-flex h-7 w-7 items-center justify-center rounded-md bg-[#2bbf7a] text-[#07130d] no-underline"
          to="/"
        >
          <Activity size={18} />
        </Link>
        <span className="h-[22px] w-px bg-[#333333]" />
        {project ? (
          <ProjectSwitcherMenu currentProject={project} projects={projects} />
        ) : (
          <span className="font-bold">Goodomics</span>
        )}
      </div>
      <button
        className="inline-flex h-[34px] min-w-[44px] cursor-pointer items-center justify-between gap-2 rounded-lg border border-[#343434] bg-[#1b1b1b] px-3 py-0 text-[#a8adb4] transition-colors hover:border-[#4a4a4a] hover:text-white md:min-w-[260px]"
        onClick={openSearch}
        type="button"
      >
        <Search size={16} />
        <span className="hidden flex-1 text-left text-sm md:block">Search...</span>
        <kbd className="hidden rounded border border-[#3b3b3b] bg-[#272727] px-1.5 py-0.5 text-[0.72rem] text-[#c4c8ce] md:block">
          ⌘K
        </kbd>
      </button>
    </header>
  );
}
