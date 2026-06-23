import { useQuery } from "@tanstack/react-query";
import { getProjectDatabaseSummary, listNamedRows } from "../api";
import { AsyncBlock, GenericRows, Page, SummaryTile } from "../components/ui";
import { formatBytes } from "../lib/utils";

export function DatabasePage({ projectId }: { projectId: string }) {
  const summary = useQuery({
    queryKey: ["database-summary", projectId],
    queryFn: () => getProjectDatabaseSummary(projectId),
  });
  const tables = useQuery({
    queryKey: ["tables"],
    queryFn: () => listNamedRows("/api/v1/database/tables"),
  });
  return (
    <Page
      title="Database"
      subtitle="Project control database and analytics store status."
    >
      <AsyncBlock query={summary} empty="No database summary available.">
        {(data) => (
          <>
            <div className="summary-grid">
              <SummaryTile
                label="SQLite"
                value={formatBytes(data.sqlite_size_bytes)}
              />
              <SummaryTile
                label="DuckDB"
                value={formatBytes(data.duckdb_size_bytes)}
              />
              <SummaryTile
                label="Files"
                value={formatBytes(data.file_size_bytes)}
              />
              <SummaryTile label="Runs" value={data.total_runs} />
              <SummaryTile label="Samples" value={data.total_samples} />
              <SummaryTile
                label="Scalar metrics"
                value={data.total_scalar_metrics}
              />
              <SummaryTile label="Payloads" value={data.total_payloads} />
            </div>
            <div className="two-column">
              <CountsTable title="Control tables" rows={data.control_tables} />
              <CountsTable
                title="Analytics tables"
                rows={data.analytics_tables}
              />
            </div>
          </>
        )}
      </AsyncBlock>
      <section className="panel">
        <h3>Editable tables</h3>
        <GenericRows query={tables} empty="No editable tables available." />
      </section>
    </Page>
  );
}

function CountsTable({
  title,
  rows,
}: {
  title: string;
  rows: { name: string; rows: number }[];
}) {
  return (
    <section className="panel">
      <h3>{title}</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Table</th>
              <th className="right">Rows</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name}>
                <td>{row.name}</td>
                <td className="right">{row.rows.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
