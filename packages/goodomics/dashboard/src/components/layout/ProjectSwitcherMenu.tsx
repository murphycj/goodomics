import { Link } from "@tanstack/react-router";
import { ChevronDown, Plus } from "lucide-react";
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

export function ProjectSwitcherMenu({
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
