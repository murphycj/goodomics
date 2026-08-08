import {
  Check,
  Copy,
  Eye,
  MoreHorizontal,
  Pencil,
  Plus,
  TextCursorInput,
  Trash2,
} from "lucide-react";
import type { InsightSummary } from "../../api";
import { insightViewLabel } from "../../lib/insightViewCatalog";
import { cn, formatDate, formatRelativeTime } from "../../lib/utils";
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

export type InsightListActions = {
  canDelete: boolean;
  canDuplicate: boolean;
  canEdit: boolean;
  onDelete: (insight: InsightSummary) => void;
  onDuplicate: (insight: InsightSummary) => void;
  onEdit: (insight: InsightSummary) => void;
  onRename: (insight: InsightSummary) => void;
  onView: (insight: InsightSummary) => void;
};

export type InsightListSelection = {
  disabled?: boolean;
  onToggle: (insightId: string, selected: boolean) => void;
  onToggleAll: (selected: boolean) => void;
  selectedIds: Set<string>;
};

/** Reusable table for browsing insights and optionally adding them to a report. */
export function InsightListTable({
  actions,
  insights,
  onAdd,
  onOpen,
  reportCounts,
  selectedInsightIds,
  selection,
}: {
  actions?: InsightListActions;
  insights: InsightSummary[];
  onAdd?: (insight: InsightSummary) => void;
  onOpen?: (insight: InsightSummary) => void;
  reportCounts?: Map<string, number>;
  selectedInsightIds?: Set<string>;
  selection?: InsightListSelection;
}) {
  const selectedCount = selection
    ? insights.filter((insight) => selection.selectedIds.has(insight.insight_id)).length
    : 0;
  const allSelected = insights.length > 0 && selectedCount === insights.length;

  return (
    <TableWrap className="mt-0">
      <Table>
        <TableHeader>
          <TableRow>
            {selection ? (
              <TableHead className="w-[44px] px-3">
                <SelectionCheckbox
                  aria-label="Select all insights"
                  checked={allSelected}
                  disabled={selection.disabled || insights.length === 0}
                  indeterminate={selectedCount > 0 && !allSelected}
                  onChange={(event) => selection.onToggleAll(event.target.checked)}
                />
              </TableHead>
            ) : null}
            <TableHead>Name</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Store</TableHead>
            <TableHead>Reports</TableHead>
            <TableHead>Created</TableHead>
            <TableHead>Last modified</TableHead>
            {onAdd || actions ? (
              <TableHead className="w-[56px] text-right">
                <span className="sr-only">Actions</span>
              </TableHead>
            ) : null}
          </TableRow>
        </TableHeader>
        <TableBody>
          {insights.map((insight) => {
            const isAdded = selectedInsightIds?.has(insight.insight_id) ?? false;
            const isSelected = selection?.selectedIds.has(insight.insight_id) ?? false;
            return (
              <TableRow
                className={cn(
                  onOpen && "cursor-pointer",
                  isSelected && "bg-[#f0f8f4] hover:bg-[#e8f4ee]",
                  onAdd && isAdded && "border-l-2 border-l-[#21a66a] bg-[#edf8f1] hover:bg-[#e5f4eb]",
                )}
                key={insight.insight_id}
                onClick={() => onOpen?.(insight)}
              >
                {selection ? (
                  <TableCell className="w-[44px] px-3">
                    <SelectionCheckbox
                      aria-label={`Select ${insight.name}`}
                      checked={isSelected}
                      disabled={selection.disabled}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(event) => selection.onToggle(insight.insight_id, event.target.checked)}
                    />
                  </TableCell>
                ) : null}
                <TableCell>
                  <div className="font-semibold">{insight.name}</div>
                  {insight.description ? (
                    <div className="mt-1 max-w-[520px] truncate text-xs text-[#657082]">
                      {insight.description}
                    </div>
                  ) : null}
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">{insightViewLabel(insight.view_kind)}</Badge>
                </TableCell>
                <TableCell className="text-[#657082]">{insight.sources.join(", ")}</TableCell>
                <TableCell className="text-[#657082]">
                  {(reportCounts?.get(insight.insight_id) ?? 0).toLocaleString()}
                </TableCell>
                <RelativeTimeCell value={insight.created_at} />
                <RelativeTimeCell value={insight.updated_at} />
                {onAdd ? (
                  <TableCell className="text-right">
                    <Button
                      aria-label={isAdded ? "Insight already added" : "Add insight to report"}
                      aria-disabled={isAdded}
                      className={cn("h-8 w-8 p-0", isAdded && "bg-transparent text-[#138a50] hover:bg-transparent")}
                      size="icon"
                      variant={isAdded ? "ghost" : "outline"}
                      onClick={(event) => {
                        event.stopPropagation();
                        if (!isAdded) onAdd(insight);
                      }}
                    >
                      {isAdded ? <Check className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
                    </Button>
                  </TableCell>
                ) : actions ? (
                  <TableCell className="text-right">
                    <InsightActionsMenu actions={actions} insight={insight} />
                  </TableCell>
                ) : null}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableWrap>
  );
}

function InsightActionsMenu({
  actions,
  insight,
}: {
  actions: InsightListActions;
  insight: InsightSummary;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          aria-label={`Actions for ${insight.name}`}
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
        <DropdownMenuItem onClick={() => actions.onView(insight)}>
          <Eye className="h-4 w-4" /> View
        </DropdownMenuItem>
        <DropdownMenuItem disabled={!actions.canEdit} onClick={() => actions.onEdit(insight)}>
          <Pencil className="h-4 w-4" /> Edit
        </DropdownMenuItem>
        <DropdownMenuItem disabled={!actions.canEdit} onClick={() => actions.onRename(insight)}>
          <TextCursorInput className="h-4 w-4" /> Rename
        </DropdownMenuItem>
        <DropdownMenuItem disabled={!actions.canDuplicate} onClick={() => actions.onDuplicate(insight)}>
          <Copy className="h-4 w-4" /> Duplicate
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-[#b42318] focus:bg-[#fff1f2]"
          disabled={!actions.canDelete}
          onClick={() => actions.onDelete(insight)}
        >
          <Trash2 className="h-4 w-4" /> Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function RelativeTimeCell({ value }: { value: string }) {
  return (
    <TableCell className="whitespace-nowrap text-[#657082]" title={formatDate(value)}>
      {formatRelativeTime(value)}
    </TableCell>
  );
}
