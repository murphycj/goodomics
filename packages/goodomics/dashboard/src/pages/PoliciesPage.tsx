import { useQuery } from "@tanstack/react-query";
import { listNamedRows } from "../api";
import { GenericRows, Page } from "../components/ui";

/** Simple QC policy registry page while policy editing is still pending. */
export function PoliciesPage() {
  const policies = useQuery({
    queryKey: ["qc-policies"],
    queryFn: () => listNamedRows("/api/v1/qc-policies"),
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
