import { useQuery } from "@tanstack/react-query";
import { listTemplates } from "../api";
import { GenericRows, Page } from "../components/ui";

export function TemplatesPage() {
  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: listTemplates,
  });
  return (
    <Page
      title="Templates"
      subtitle="Edit DB-backed templates and export YAML or JSON."
    >
      <GenericRows
        query={templates}
        empty="Create a template to begin editing."
      />
    </Page>
  );
}
