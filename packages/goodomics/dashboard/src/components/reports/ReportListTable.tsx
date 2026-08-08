import { Copy, Eye, MoreHorizontal, Pencil, TextCursorInput, Trash2 } from "lucide-react";
import type { ReportSummary } from "../../api";
import { formatDate, formatRelativeTime } from "../../lib/utils";
import {
  Badge,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  SelectionCheckbox,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrap,
} from "../ui";

export type ReportListActions = {
  canDelete: boolean;
  canDuplicate: boolean;
  canEdit: boolean;
  onDelete: (report: ReportSummary) => void;
  onDuplicate: (report: ReportSummary) => void;
  onEdit: (report: ReportSummary) => void;
  onRename: (report: ReportSummary) => void;
  onView: (report: ReportSummary) => void;
};

export type ReportListSelection = {
  disabled?: boolean;
  onToggle: (reportId: string, selected: boolean) => void;
  onToggleAll: (selected: boolean) => void;
  selectedIds: Set<string>;
};

/** Reusable table for browsing saved project reports. */
export function ReportListTable({
  actions,
  defaultReportId,
  onOpen,
  reports,
  selection,
}: {
  actions: ReportListActions;
  defaultReportId: string | null;
  onOpen: (report: ReportSummary) => void;
  reports: ReportSummary[];
  selection: ReportListSelection;
}) {
  const selectedCount = reports.filter((report) => selection.selectedIds.has(report.report_id)).length;
  const allSelected = reports.length > 0 && selectedCount === reports.length;

  return (
    <TableWrap className="mt-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[44px] px-3">
              <SelectionCheckbox
                aria-label="Select all reports"
                checked={allSelected}
                disabled={selection.disabled || reports.length === 0}
                indeterminate={selectedCount > 0 && !allSelected}
                onChange={(event) => selection.onToggleAll(event.target.checked)}
              />
            </TableHead>
            <TableHead>Name</TableHead>
            <TableHead>Insights</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Created</TableHead>
            <TableHead>Last modified</TableHead>
            <TableHead className="w-[56px] text-right"><span className="sr-only">Actions</span></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {reports.map((report) => {
            const isSelected = selection.selectedIds.has(report.report_id);
            return (
              <TableRow
                className={isSelected ? "cursor-pointer bg-[#f0f8f4] hover:bg-[#e8f4ee]" : "cursor-pointer"}
                key={report.report_id}
                onClick={() => onOpen(report)}
              >
                <TableCell className="w-[44px] px-3">
                  <SelectionCheckbox
                    aria-label={`Select ${report.name}`}
                    checked={isSelected}
                    disabled={selection.disabled}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => selection.onToggle(report.report_id, event.target.checked)}
                  />
                </TableCell>
                <TableCell>
                  <div className="font-semibold">{report.name}</div>
                  {report.description ? (
                    <div className="mt-1 max-w-[620px] truncate text-xs text-[#657082]">{report.description}</div>
                  ) : null}
                </TableCell>
                <TableCell className="text-[#657082]">{report.insight_count.toLocaleString()}</TableCell>
                <TableCell>
                  {report.report_id === defaultReportId ? <Badge>Default view</Badge> : <Badge variant="outline">Saved</Badge>}
                </TableCell>
                <RelativeTimeCell value={report.created_at} />
                <RelativeTimeCell value={report.updated_at} />
                <TableCell className="text-right">
                  <ReportActionsMenu actions={actions} report={report} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableWrap>
  );
}

function ReportActionsMenu({ actions, report }: { actions: ReportListActions; report: ReportSummary }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          aria-label={`Actions for ${report.name}`}
          className="h-8 w-8"
          size="icon"
          variant="ghost"
          onClick={(event) => event.stopPropagation()}
        >
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="min-w-[190px]"
        onClick={(event) => event.stopPropagation()}
      >
        <DropdownMenuItem onClick={() => actions.onView(report)}><Eye className="h-4 w-4" /> View</DropdownMenuItem>
        <DropdownMenuItem disabled={!actions.canEdit} onClick={() => actions.onEdit(report)}><Pencil className="h-4 w-4" /> Edit</DropdownMenuItem>
        <DropdownMenuItem disabled={!actions.canEdit} onClick={() => actions.onRename(report)}><TextCursorInput className="h-4 w-4" /> Rename</DropdownMenuItem>
        <DropdownMenuItem disabled={!actions.canDuplicate} onClick={() => actions.onDuplicate(report)}><Copy className="h-4 w-4" /> Duplicate</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-[#b42318] focus:bg-[#fff1f2]"
          disabled={!actions.canDelete}
          onClick={() => actions.onDelete(report)}
        >
          <Trash2 className="h-4 w-4" /> Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function RelativeTimeCell({ value }: { value: string }) {
  return <TableCell className="whitespace-nowrap text-[#657082]" title={formatDate(value)}>{formatRelativeTime(value)}</TableCell>;
}
