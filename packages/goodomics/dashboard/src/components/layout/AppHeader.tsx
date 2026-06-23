import { Link } from "@tanstack/react-router";
import { Activity, ChevronDown, Plus, Search } from "lucide-react";
import { useState } from "react";
import type { GoodomicsProject } from "../../api";
import { CreateProjectModal } from "../projects/CreateProjectModal";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";

export function AppHeader({
  onOpenSearch,
  project,
  projects,
}: {
  onOpenSearch: () => void;
  project?: GoodomicsProject;
  projects: GoodomicsProject[];
}) {
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
          <ProjectSwitcher currentProject={project} projects={projects} />
        ) : (
          <span className="font-bold">Goodomics</span>
        )}
      </div>
      <button
        className="inline-flex h-[34px] min-w-[44px] cursor-pointer items-center justify-between gap-2 rounded-lg border border-[#343434] bg-[#1b1b1b] px-3 py-0 text-[#a8adb4] transition-colors hover:border-[#4a4a4a] hover:text-white md:min-w-[260px]"
        onClick={onOpenSearch}
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

function ProjectSwitcher({
  currentProject,
  projects,
}: {
  currentProject: GoodomicsProject;
  projects: GoodomicsProject[];
}) {
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className="flex min-w-0 cursor-pointer items-center gap-2 border-0 bg-transparent p-0 text-[#f6f6f6] hover:text-white"
            type="button"
          >
            <span className="grid min-w-0 leading-tight">
              <strong className="overflow-hidden text-ellipsis whitespace-nowrap">
                {currentProject.name}
              </strong>
            </span>
            <ChevronDown size={16} />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuLabel>Projects</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {projects.map((project) => (
            <DropdownMenuItem key={project.project_id} asChild>
              <Link
                className="text-[#1d2430] no-underline"
                to="/project/$projectId"
                params={{ projectId: project.project_id }}
              >
                <span className="grid min-w-0">
                  <span className="overflow-hidden text-ellipsis whitespace-nowrap font-medium">
                    {project.name}
                  </span>
                </span>
              </Link>
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setCreateOpen(true)}>
            <Plus size={16} />
            Create new project
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {createOpen && <CreateProjectModal onClose={() => setCreateOpen(false)} />}
    </>
  );
}
