import { useQuery } from "@tanstack/react-query";
import { listNamedRows } from "../api";
import { GenericRows, Page } from "../components/ui";

export function CohortsPage() {
  const cohorts = useQuery({
    queryKey: ["cohorts"],
    queryFn: () => listNamedRows("/api/v1/cohorts"),
  });
  return (
    <Page
      title="Cohorts"
      subtitle="Group runs and samples for cohort-aware QC."
    >
      <GenericRows query={cohorts} empty="No cohorts configured." />
    </Page>
  );
}
