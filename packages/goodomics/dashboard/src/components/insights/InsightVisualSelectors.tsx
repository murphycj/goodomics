import {
  Activity,
  BarChart3,
  Boxes,
  ChartNoAxesCombined,
  ChevronDown,
  CircleDotDashed,
  Clock3,
  Dna,
  GitCompareArrows,
  Grid3X3,
  Network,
  Sigma,
  Table2,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import type { QueryKind, ViewKind } from "../../lib/insightSchemas";
import { compatibleViews, titleCase } from "../../lib/insightBuilder";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui";
import { InsightViewThumbnail } from "./InsightViewThumbnail";

type AnalysisType = {
  kind: QueryKind;
  label: string;
  description: string;
  group: "Explore data" | "Compare and arrange" | "Biological views";
  icon: LucideIcon;
};

export const ANALYSIS_TYPES: AnalysisType[] = [
  { kind: "rows", label: "Build a table", description: "Choose fields and preserve one row per entity.", group: "Explore data", icon: Table2 },
  { kind: "summary", label: "Summarize groups", description: "Group entities and calculate descriptive totals.", group: "Explore data", icon: Sigma },
  { kind: "distribution", label: "View a distribution", description: "Inspect values, ranges, and descriptive summaries.", group: "Explore data", icon: BarChart3 },
  { kind: "relationship", label: "Compare two fields", description: "Match two measures by a shared identity.", group: "Compare and arrange", icon: GitCompareArrows },
  { kind: "series", label: "Show a profile or trend", description: "Arrange measurements along an ordered position.", group: "Compare and arrange", icon: ChartNoAxesCombined },
  { kind: "matrix", label: "Build a matrix", description: "Place raw values across row and column identities.", group: "Compare and arrange", icon: Grid3X3 },
  { kind: "alteration_matrix", label: "Alteration matrix", description: "Compare feature alterations across eligible entities.", group: "Biological views", icon: Boxes },
  { kind: "variant_position", label: "Variant positions", description: "Show recurrence along a transcript or protein.", group: "Biological views", icon: CircleDotDashed },
  { kind: "genome_profile", label: "Genomic profile", description: "Lay out measurements across genomic coordinates.", group: "Biological views", icon: Dna },
  { kind: "timeline", label: "Subject timeline", description: "Arrange subject events over absolute or relative time.", group: "Biological views", icon: Clock3 },
  { kind: "association", label: "Association matrix", description: "Describe feature co-occurrence and eligibility.", group: "Biological views", icon: Network },
  { kind: "survival", label: "Survival", description: "Configure provider-backed time-to-event analysis.", group: "Biological views", icon: Activity },
];

const GROUPS: AnalysisType["group"][] = ["Explore data", "Compare and arrange", "Biological views"];

export function analysisType(kind: QueryKind) {
  return ANALYSIS_TYPES.find((item) => item.kind === kind) ?? ANALYSIS_TYPES[0];
}

export function AnalysisTypePicker({
  disabled,
  kind,
  onChange,
}: {
  disabled: boolean;
  kind: QueryKind;
  onChange: (kind: QueryKind) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = analysisType(kind);
  const Icon = selected.icon;
  return (
    <>
      <ToolbarField label="Analysis type">
        <Button
          className="h-10 min-w-[205px] justify-between border-[#ccd6e2] bg-white px-3 text-[#253343] hover:bg-[#f7faf9]"
          disabled={disabled}
          variant="outline"
          onClick={() => setOpen(true)}
        >
          <span className="flex min-w-0 items-center gap-2">
            <Icon className="h-4 w-4 shrink-0 text-[#16784a]" />
            <span className="truncate">{selected.label}</span>
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-[#657082]" />
        </Button>
      </ToolbarField>
      <AnalysisTypeDialog
        kind={kind}
        open={open}
        onOpenChange={setOpen}
        onSelect={(nextKind) => {
          onChange(nextKind);
          setOpen(false);
        }}
      />
    </>
  );
}

/** Shared analysis chooser used by both the index entry flow and the builder. */
export function AnalysisTypeDialog({
  kind,
  open,
  onOpenChange,
  onSelect,
}: {
  kind?: QueryKind;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (kind: QueryKind) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[88vh] max-w-[1040px] flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="shrink-0 border-b border-[#dce3eb] px-5 py-4 pr-16">
          <DialogTitle>What do you want to explore?</DialogTitle>
          <DialogDescription>
            Choose an analysis type. Goodomics will show the inputs and visual views that work with it.
          </DialogDescription>
        </DialogHeader>
        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          {GROUPS.map((group) => (
            <section className="mb-4 last:mb-0" key={group}>
              <h3 className="mb-2 text-sm font-semibold text-[#253343]">{group}</h3>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {ANALYSIS_TYPES.filter((item) => item.group === group).map((item) => {
                  const selectedItem = item.kind === kind;
                  return (
                    <button
                      className={[
                        "group grid min-h-[76px] grid-cols-[92px_minmax(0,1fr)] overflow-hidden rounded-lg border bg-white text-left transition-all",
                        selectedItem
                          ? "border-[#21a66a] ring-2 ring-[#21a66a]/15"
                          : "border-[#d6dee8] hover:border-[#9eb5aa] hover:shadow-sm",
                      ].join(" ")}
                      key={item.kind}
                      type="button"
                      onClick={() => onSelect(item.kind)}
                    >
                      <div className="h-full min-h-[76px] border-r border-[#e5eaf0] bg-[#f8fafc] p-2.5">
                        <InsightViewThumbnail
                          className="h-full w-full"
                          decorative
                          kind={analysisTypeView(item.kind)}
                        />
                      </div>
                      <div className="min-w-0 self-center px-3 py-2.5">
                        <div className="flex items-center text-sm font-semibold text-[#1f2937]">
                          {item.label}
                          {item.kind === "survival" ? (
                            <span className="ml-auto rounded bg-[#fff4d7] px-1.5 py-0.5 text-[10px] font-semibold uppercase text-[#8a5c08]">Provider</span>
                          ) : null}
                        </div>
                        <p className="mb-0 mt-1 text-[11px] leading-4 text-[#657082]">{item.description}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function ViewPicker({
  compact = false,
  disabled,
  kind,
  queryKind,
  onChange,
}: {
  compact?: boolean;
  disabled: boolean;
  kind: ViewKind;
  queryKind: QueryKind;
  onChange: (kind: ViewKind) => void;
}) {
  const views = compatibleViews(queryKind);
  const [open, setOpen] = useState(false);
  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          className={[
            "h-10 justify-between border-[#ccd6e2] bg-white px-3 text-[#253343] hover:bg-[#f7faf9]",
            compact ? "min-w-[145px]" : "min-w-[175px]",
          ].join(" ")}
          disabled={disabled}
          variant="outline"
        >
          <span className="flex min-w-0 items-center gap-2">
            <InsightViewThumbnail className="h-6 w-8" decorative kind={kind} />
            <span className="truncate">{viewLabel(kind)}</span>
          </span>
          <ChevronDown className="h-4 w-4 text-[#657082]" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[280px] p-1.5">
        <div className="px-2 py-1.5 text-xs font-semibold uppercase tracking-wide text-[#657082]">Compatible views</div>
        <div className="space-y-0.5">
          {views.map((view) => (
            <DropdownMenuItem
              className={[
                "flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-left",
                view === kind ? "bg-[#edf8f2] text-[#176a43]" : "text-[#253343] focus:bg-[#f3f6f8]",
              ].join(" ")}
              key={view}
              onSelect={() => {
                onChange(view);
                setOpen(false);
              }}
            >
              <InsightViewThumbnail className="h-9 w-12" decorative kind={view} />
              <span className="min-w-0 flex-1 truncate text-sm font-medium">{viewLabel(view)}</span>
            </DropdownMenuItem>
          ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function ToolbarField({ children, label }: { children: ReactNode; label: string }) {
  return <label className="flex flex-col gap-1"><span className="text-[11px] font-bold uppercase tracking-wide text-[#657082]">{label}</span>{children}</label>;
}

export function viewLabel(kind: ViewKind) {
  if (kind === "metric") return "Number";
  if (kind === "association_matrix") return "Association matrix";
  return titleCase(kind);
}

function analysisTypeView(kind: QueryKind): ViewKind {
  if (kind === "rows") return "table";
  if (kind === "summary") return "bar";
  if (kind === "distribution") return "histogram";
  if (kind === "relationship") return "scatter";
  if (kind === "series") return "line";
  if (kind === "matrix") return "heatmap";
  return compatibleViews(kind)[0];
}
