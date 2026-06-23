import { useQuery } from "@tanstack/react-query";
import type { GoodomicsSample } from "../api";
import { getProjectSample } from "../api";
import { AsyncBlock, Card, CardContent, CardHeader, CardTitle, Detail, Page } from "../components/ui";

export function SampleDetailPage({
  projectId,
  sampleId,
}: {
  projectId: string;
  sampleId: string;
}) {
  const sample = useQuery({
    queryKey: ["project-sample", projectId, sampleId],
    queryFn: () => getProjectSample(projectId, sampleId),
  });

  return (
    <Page
      title={sample.data?.sample_name ?? sampleId}
      subtitle="Sample identity and stored metadata."
    >
      <AsyncBlock query={sample} empty="Sample not found.">
        {(data: GoodomicsSample) => (
          <>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
              <Detail label="Sample ID" value={data.sample_id} />
              <Detail label="Sample name" value={data.sample_name ?? "—"} />
              <Detail label="Project ref" value={data.project_id ?? "—"} />
              <Detail label="Subject" value={data.subject_id ?? "—"} />
              <Detail label="External ID" value={data.external_id ?? "—"} />
            </div>
            <Card>
              <CardHeader>
                <CardTitle>Metadata</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="mt-0 overflow-auto rounded-lg border border-[#dce3eb] bg-[#f8fafb] p-4 text-sm shadow-[0_14px_34px_rgb(25_32_43/0.05)]">
                  {JSON.stringify(data.metadata_json, null, 2)}
                </pre>
              </CardContent>
            </Card>
          </>
        )}
      </AsyncBlock>
    </Page>
  );
}
