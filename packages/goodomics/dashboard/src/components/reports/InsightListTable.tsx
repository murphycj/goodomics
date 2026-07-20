import { Check, Plus } from "lucide-react";
import type { SavedInsight } from "../../api";
import { cn, formatDate } from "../../lib/utils";
import {
  Badge,
  Button,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableWrap,
} from "../ui";
import { isRecord } from "./reportUtils";

type Store = "metadata" | "analytics";

/** Reusable table for browsing insights and optionally adding them to a report. */
export function InsightListTable({
  insights,
  onAdd,
  onOpen,
  reportCounts,
  selectedInsightIds,
}: {
  insights: SavedInsight[];
  onAdd?: (insight: SavedInsight) => void;
  onOpen?: (insight: SavedInsight) => void;
  reportCounts?: Map<string, number>;
  selectedInsightIds?: Set<string>;
}) {
  return (
    <TableWrap className="mt-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Store</TableHead>
            <TableHead>Reports</TableHead>
            <TableHead>Last modified</TableHead>
            {onAdd ? (
              <TableHead className="w-[56px] text-right">
                <span className="sr-only">Add to report</span>
              </TableHead>
            ) : null}
          </TableRow>
        </TableHeader>
        <TableBody>
          {insights.map((insight) => {
            const query = isRecord(insight.config.query) ? insight.config.query : {};
            const source = parseSource(query.source);
            const isSelected = selectedInsightIds?.has(insight.insight_id) ?? false;
            return (
              <TableRow
                className={cn(
                  onOpen && "cursor-pointer",
                  onAdd &&
                    isSelected &&
                    "border-l-2 border-l-[#21a66a] bg-[#edf8f1] hover:bg-[#e5f4eb]",
                )}
                key={insight.insight_id}
                onClick={() => onOpen?.(insight)}
              >
                <TableCell>
                  <div className="font-semibold">{insight.name}</div>
                  {insight.description ? (
                    <div className="mt-1 max-w-[520px] truncate text-xs text-[#657082]">
                      {insight.description}
                    </div>
                  ) : null}
                </TableCell>
                <TableCell>
                  <Badge variant="secondary">
                    {String(insight.config.visualization ?? "table")}
                  </Badge>
                </TableCell>
                <TableCell className="text-[#657082]">
                  {source.store}.{source.table || "query"}
                </TableCell>
                <TableCell className="text-[#657082]">
                  {(reportCounts?.get(insight.insight_id) ?? 0).toLocaleString()}
                </TableCell>
                <TableCell className="text-[#657082]">
                  {formatDate(insight.updated_at, { style: "date" })}
                </TableCell>
                {onAdd ? (
                  <TableCell className="text-right">
                    <Button
                      aria-label={
                        isSelected ? "Insight already added" : "Add insight to report"
                      }
                      aria-disabled={isSelected}
                      className={cn(
                        "h-8 w-8 p-0",
                        isSelected &&
                          "bg-transparent text-[#138a50] hover:bg-transparent",
                      )}
                      size="icon"
                      variant={isSelected ? "ghost" : "outline"}
                      onClick={(event) => {
                        event.stopPropagation();
                        if (!isSelected) onAdd(insight);
                      }}
                    >
                      {isSelected ? (
                        <Check className="h-4 w-4" />
                      ) : (
                        <Plus className="h-4 w-4" />
                      )}
                    </Button>
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

function parseSource(value: unknown): { store: Store; table: string } {
  if (isRecord(value)) {
    return {
      store: value.store === "metadata" ? "metadata" : "analytics",
      table: typeof value.table === "string" ? value.table : "",
    };
  }
  if (typeof value === "string" && value.includes(".")) {
    const [store, table] = value.split(".", 2);
    return { store: store === "metadata" ? "metadata" : "analytics", table };
  }
  return { store: "analytics", table: typeof value === "string" ? value : "" };
}
