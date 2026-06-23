import { useQuery } from "@tanstack/react-query";
import type { GoodomicsSample } from "../api";
import { getProjectSample } from "../api";
import { AsyncBlock, Detail, Page } from "../components/ui";

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
            <div className="details-grid">
              <Detail label="Sample ID" value={data.sample_id} />
              <Detail label="Sample name" value={data.sample_name ?? "—"} />
              <Detail label="Project ref" value={data.project_id ?? "—"} />
              <Detail label="Subject" value={data.subject_id ?? "—"} />
              <Detail label="External ID" value={data.external_id ?? "—"} />
            </div>
            <section className="panel">
              <h3>Metadata</h3>
              <pre className="json-block">
                {JSON.stringify(data.metadata_json, null, 2)}
              </pre>
            </section>
          </>
        )}
      </AsyncBlock>
    </Page>
  );
}
