import { Detail, Page } from "../components/ui";

export function SettingsPage({ projectId }: { projectId: string }) {
  return (
    <Page title="Settings" subtitle="Dashboard and API configuration.">
      <div className="panel">
        <div className="details-grid">
          <Detail label="Project ref" value={projectId} />
          <Detail label="API namespace" value="/api/v1" />
        </div>
      </div>
    </Page>
  );
}
