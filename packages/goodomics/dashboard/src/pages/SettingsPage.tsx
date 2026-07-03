import { useMutation, useQuery } from "@tanstack/react-query";
import { getProject, listReports, patchProject } from "../api";
import {
  Card,
  CardContent,
  Detail,
  Label,
  Page,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui";
import { queryClient } from "../lib/queryClient";

const NO_DEFAULT_REPORT = "__none__";

/** Project settings page for API context and default report selection. */
export function SettingsPage({ projectId }: { projectId: string }) {
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
  });
  const reports = useQuery({
    queryKey: ["reports", projectId],
    queryFn: () => listReports(projectId),
  });
  const defaultReport = useMutation({
    mutationFn: (reportId: string | null) =>
      patchProject(projectId, { default_report_id: reportId }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
  });
  return (
    <Page title="Settings" subtitle="Dashboard and API configuration.">
      <Card>
        <CardContent className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
          <Detail label="Project ref" value={projectId} />
          <Detail label="API namespace" value="/api/v1" />
          <div className="space-y-1.5">
            <Label>Default report</Label>
            <Select
              value={project.data?.default_report_id ?? NO_DEFAULT_REPORT}
              onValueChange={(value) =>
                defaultReport.mutate(value === NO_DEFAULT_REPORT ? null : value)
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="Choose report" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_DEFAULT_REPORT}>No default report</SelectItem>
                {(reports.data ?? []).map((report) => (
                  <SelectItem key={report.report_id} value={report.report_id}>
                    {report.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>
    </Page>
  );
}
