import { useQuery } from "@tanstack/react-query";
import { listNamedRows } from "../api";
import { GenericRows, Page } from "../components/ui";

export function ReportsPage() {
  const reports = useQuery({
    queryKey: ["reports"],
    queryFn: () => listNamedRows("/api/v1/database/tables/reports/rows"),
  });
  return (
    <Page title="Reports" subtitle="Rendered standalone reports.">
      <GenericRows query={reports} empty="No rendered reports yet." />
    </Page>
  );
}
