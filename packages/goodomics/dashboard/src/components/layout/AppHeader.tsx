import { Link } from "@tanstack/react-router";
import { Search, Sparkles } from "lucide-react";
import type { CSSProperties } from "react";
import type { GoodomicsProject } from "../../api";
import { useSearch } from "../search/SearchProvider";
import { ProjectSwitcherMenu } from "./ProjectSwitcherMenu";

/** Fixed top bar with project switching, Ask AI, and global search controls. */
export function AppHeader({
  askInset,
  project,
  projects,
}: {
  askInset: number;
  project?: GoodomicsProject;
  projects: GoodomicsProject[];
}) {
  const { openAsk, openSearch } = useSearch();

  return (
    <header
      className="fixed left-0 right-0 top-0 z-30 flex h-12 items-center justify-between gap-4 border-b border-[#2a2a2a] bg-[#111111] px-4 text-[#f6f6f6] transition-[right] duration-200 ease-out md:right-[var(--ask-ai-inset)]"
      style={{ "--ask-ai-inset": `${askInset}px` } as CSSProperties}
    >
      <div className="flex min-w-0 items-center gap-3">
        <Link
          aria-label="Goodomics home"
          className="inline-flex h-7 w-7 items-center justify-center overflow-hidden rounded-md no-underline"
          to="/"
        >
          <img alt="" className="h-full w-full" src="/goodomics.svg" />
        </Link>
        <span className="h-[22px] w-px bg-[#333333]" />
        {project ? (
          <ProjectSwitcherMenu currentProject={project} projects={projects} />
        ) : (
          <span className="font-bold">Goodomics</span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <button
          className="inline-flex h-[34px] cursor-pointer items-center gap-1.5 rounded-lg border border-[#343434] bg-[#1b1b1b] px-3 py-0 text-sm font-medium text-[#d2d8df] transition-colors hover:border-[#58c98a] hover:text-white"
          onClick={() => openAsk()}
          type="button"
        >
          <Sparkles size={15} />
          <span>AI</span>
        </button>
        <button
          className="inline-flex h-[34px] min-w-[44px] cursor-pointer items-center justify-between gap-2 rounded-lg border border-[#343434] bg-[#1b1b1b] px-3 py-0 text-[#a8adb4] transition-colors hover:border-[#4a4a4a] hover:text-white md:min-w-[260px]"
          onClick={() => openSearch()}
          type="button"
        >
          <Search size={16} />
          <span className="hidden flex-1 text-left text-sm md:block">Search...</span>
          <kbd className="hidden rounded border border-[#3b3b3b] bg-[#272727] px-1.5 py-0.5 text-[0.72rem] text-[#c4c8ce] md:block">
            ⌘K
          </kbd>
        </button>
      </div>
    </header>
  );
}
