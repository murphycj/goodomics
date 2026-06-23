import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { listProjects } from "../api";
import { CreateProjectButton } from "../components/projects/CreateProjectModal";
import { useSearch } from "../components/search/SearchProvider";
import {
  AsyncBlock,
  CopyButton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrap,
} from "../components/ui";
import { formatDate } from "../lib/utils";

export function HomePage() {
  const projects = useQuery({ queryKey: ["projects"], queryFn: listProjects });
  const { openSearch } = useSearch();
  const navigate = useNavigate();

  const openProject = (projectId: string) => {
    void navigate({ to: "/project/$projectId", params: { projectId } });
  };

  return (
    <div className="grid gap-8">
      <section className="pb-3 pt-6 md:pt-13">
        <h1 className="m-0 text-[clamp(2.25rem,5vw,4.2rem)] font-semibold leading-none tracking-normal text-[#1d2430]">
          Goodomics
        </h1>
        <button
          className="mt-6 flex h-[54px] w-full max-w-[720px] cursor-pointer items-center justify-between gap-3 rounded-lg border border-[#d8dee7] bg-white px-4 text-[#657082] shadow-[0_16px_42px_rgb(25_32_43/0.08)] transition-colors hover:border-[#c9d1dc] hover:text-[#1d2430]"
          onClick={openSearch}
          type="button"
        >
          <Search size={18} />
          <span className="flex-1 text-left">Search samples across the database...</span>
          <kbd className="rounded border border-[#dce3eb] bg-[#f8fafb] px-1.5 py-0.5 text-[0.72rem] text-[#657082]">
            ⌘K
          </kbd>
        </button>
      </section>
      <section className="min-w-0">
        <div className="mb-3 flex min-w-0 flex-col items-start justify-between gap-4 md:flex-row md:items-center">
          <div>
            <h2 className="m-0 text-[1.5rem] font-semibold tracking-normal text-[#1d2430]">
              Projects
            </h2>
            <p className="mb-0 mt-1 text-[#657082]">
              Choose a workspace to inspect runs, samples, reports, and data
              stores.
            </p>
          </div>
          <CreateProjectButton />
        </div>
        <AsyncBlock query={projects} empty="No projects have been created yet.">
          {(items) => (
            <TableWrap>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Project ID</TableHead>
                    <TableHead className="text-right">Runs</TableHead>
                    <TableHead className="text-right">Samples</TableHead>
                    <TableHead>Latest activity</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((project) => (
                    <TableRow
                      className="cursor-pointer hover:!bg-[#eef8f2] focus-visible:outline-2 focus-visible:outline-[#8edeb4] focus-visible:outline-offset-[-2px]"
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
                      <TableCell className="font-bold">{project.name}</TableCell>
                      <TableCell>
                        <div className="inline-flex items-center gap-1.5">
                          <span className="font-mono">{project.project_id}</span>
                          <CopyButton
                            label={`Copy project ref ${project.project_id}`}
                            value={project.project_id}
                          />
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        {project.run_count.toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right">
                        {project.sample_count.toLocaleString()}
                      </TableCell>
                      <TableCell>
                        {project.latest_activity_at
                          ? formatDate(project.latest_activity_at)
                          : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableWrap>
          )}
        </AsyncBlock>
      </section>
    </div>
  );
}
