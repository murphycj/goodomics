import { Link } from "@tanstack/react-router";
import { Activity, ChevronDown, Plus, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { GoodomicsProject } from "../../api";
import { CreateProjectModal } from "../projects/CreateProjectModal";

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
    <header className="app-header">
      <div className="brand-area">
        <Link className="brand-mark" to="/">
          <Activity size={18} />
        </Link>
        <span className="header-divider" />
        {project ? (
          <ProjectSwitcher currentProject={project} projects={projects} />
        ) : (
          <span className="header-home-label">Goodomics</span>
        )}
      </div>
      <button className="header-search" onClick={onOpenSearch} type="button">
        <Search size={16} />
        <span>Search...</span>
        <kbd>⌘K</kbd>
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
  const [open, setOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const switcherRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!switcherRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  return (
    <div className="project-switcher" ref={switcherRef}>
      <button
        className="project-switcher-trigger"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <span>
          <strong>{currentProject.name}</strong>
        </span>
        <ChevronDown size={16} />
      </button>
      {open && (
        <div className="project-menu">
          <div className="project-menu-heading">Projects</div>
          {projects.map((project) => (
            <Link
              className="project-menu-item"
              key={project.project_id}
              onClick={() => setOpen(false)}
              to="/project/$projectId"
              params={{ projectId: project.project_id }}
            >
              <span>{project.name}</span>
            </Link>
          ))}
          <button
            className="project-menu-create"
            onClick={() => {
              setOpen(false);
              setCreateOpen(true);
            }}
            type="button"
          >
            <Plus size={16} /> Create new project
          </button>
        </div>
      )}
      {createOpen && (
        <CreateProjectModal onClose={() => setCreateOpen(false)} />
      )}
    </div>
  );
}
