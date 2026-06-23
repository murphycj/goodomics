import { useQuery } from "@tanstack/react-query";
import { getProjectDatabaseSummary, listNamedRows } from "../api";
import {
  AsyncBlock,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  GenericRows,
  Page,
  SummaryTile,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrap,
} from "../components/ui";
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
            <div className="my-4 grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-3">
              <SummaryTile label="SQLite" value={formatBytes(data.sqlite_size_bytes)} />
              <SummaryTile label="DuckDB" value={formatBytes(data.duckdb_size_bytes)} />
              <SummaryTile label="Files" value={formatBytes(data.file_size_bytes)} />
              <SummaryTile label="Runs" value={data.total_runs} />
              <SummaryTile label="Samples" value={data.total_samples} />
              <SummaryTile label="Scalar metrics" value={data.total_scalar_metrics} />
              <SummaryTile label="Payloads" value={data.total_payloads} />
            </div>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-4">
              <CountsTable title="Control tables" rows={data.control_tables} />
              <CountsTable title="Analytics tables" rows={data.analytics_tables} />
            </div>
          </>
        )}
      </AsyncBlock>
      <Card>
        <CardHeader>
          <CardTitle>Editable tables</CardTitle>
        </CardHeader>
        <CardContent>
          <GenericRows query={tables} empty="No editable tables available." />
        </CardContent>
      </Card>
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
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <TableWrap className="mt-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Table</TableHead>
                <TableHead className="text-right">Rows</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.name}>
                  <TableCell>{row.name}</TableCell>
                  <TableCell className="text-right">
                    {row.rows.toLocaleString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableWrap>
      </CardContent>
    </Card>
  );
}
