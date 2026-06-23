import { Card, CardContent, Detail, Page } from "../components/ui";

export function SettingsPage({ projectId }: { projectId: string }) {
  return (
    <Page title="Settings" subtitle="Dashboard and API configuration.">
      <Card>
        <CardContent className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3">
          <Detail label="Project ref" value={projectId} />
          <Detail label="API namespace" value="/api/v1" />
        </CardContent>
      </Card>
    </Page>
  );
}
