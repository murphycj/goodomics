import { useQuery } from "@tanstack/react-query";
import { listNamedRows } from "../api";
import { GenericRows, Page } from "../components/ui";

/** Simple QC policy registry page while policy editing is still pending. */
export function PoliciesPage({ projectId }: { projectId: string }) {
  const policies = useQuery({
    queryKey: ["qc-policies", projectId],
    queryFn: () =>
      listNamedRows(
        `/api/v1/projects/${encodeURIComponent(projectId)}/qc-policies`,
      ),
  });
  return (
    <Page
      title="QC policies"
      subtitle="Manage threshold sets for quality decisions."
    >
      <GenericRows query={policies} empty="No QC policies configured." />
    </Page>
  );
}
