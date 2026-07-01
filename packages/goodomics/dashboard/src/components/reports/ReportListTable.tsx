import type { SavedReport } from "../../api";
import { formatDate } from "../../lib/utils";
import {
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrap,
} from "../ui";
import { readReportItems } from "./reportUtils";

/** Reusable table for browsing saved project reports. */
export function ReportListTable({
  defaultReportId,
  onOpen,
  reports,
}: {
  defaultReportId: string | null;
  onOpen: (report: SavedReport) => void;
  reports: SavedReport[];
}) {
  return (
    <TableWrap className="mt-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Insights</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
            <TableHead>Last modified</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {reports.map((report) => (
            <TableRow
              className="cursor-pointer"
              key={report.report_id}
              onClick={() => onOpen(report)}
            >
              <TableCell>
                <div className="font-semibold">{report.name}</div>
                {report.description ? (
                  <div className="mt-1 max-w-[620px] truncate text-xs text-[#657082]">
                    {report.description}
                  </div>
                ) : null}
              </TableCell>
              <TableCell className="text-[#657082]">
                {readReportItems(report.config).length.toLocaleString()}
              </TableCell>
              <TableCell>
                {report.report_id === defaultReportId ? (
                  <Badge>Default view</Badge>
                ) : (
                  <Badge variant="outline">Saved</Badge>
                )}
              </TableCell>
              <TableCell className="text-[#657082]">
                {formatDate(report.created_at, { style: "date" })}
              </TableCell>
              <TableCell className="text-[#657082]">
                {formatDate(report.updated_at, { style: "date" })}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableWrap>
  );
}
