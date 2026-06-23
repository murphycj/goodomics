import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { useState } from "react";
import { listProjects } from "../api";
import { CreateProjectButton } from "../components/projects/CreateProjectModal";
import { SearchOverlay } from "../components/search/SearchOverlay";
import { AsyncBlock } from "../components/ui";
import { formatDate } from "../lib/utils";

export function HomePage() {
  const [searchOpen, setSearchOpen] = useState(false);
  const projects = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const navigate = useNavigate();

  const openProject = (projectId: string) => {
    void navigate({ to: "/project/$projectId", params: { projectId } });
  };

  return (
    <div className="home-page">
      <section className="home-intro">
        <h1>Goodomics</h1>
        <button
          className="home-search"
          onClick={() => setSearchOpen(true)}
          type="button"
        >
          <Search size={18} />
          <span>Search samples across the database...</span>
          <kbd>⌘K</kbd>
        </button>
      </section>
      <section className="home-projects">
        <div className="section-heading">
          <div>
            <h2>Projects</h2>
            <p>
              Choose a workspace to inspect runs, samples, reports, and data
              stores.
            </p>
          </div>
          <CreateProjectButton />
        </div>
        <AsyncBlock query={projects} empty="No projects have been created yet.">
          {(items) => (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Slug</th>
                    <th>Project ref</th>
                    <th className="right">Runs</th>
                    <th className="right">Samples</th>
                    <th>Latest activity</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((project) => (
                    <tr
                      className="clickable-row"
                      key={project.project_id}
                      onClick={() => openProject(project.project_id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          openProject(project.project_id);
                        }
                      }}
                      role="link"
                      tabIndex={0}
                    >
                      <td className="strong">{project.name}</td>
                      <td>{project.slug ?? "—"}</td>
                      <td className="mono">{project.project_id}</td>
                      <td className="right">
                        {project.run_count.toLocaleString()}
                      </td>
                      <td className="right">
                        {project.sample_count.toLocaleString()}
                      </td>
                      <td>
                        {project.latest_activity_at
                          ? formatDate(project.latest_activity_at)
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AsyncBlock>
      </section>
      <SearchOverlay onClose={() => setSearchOpen(false)} open={searchOpen} />
    </div>
  );
}
