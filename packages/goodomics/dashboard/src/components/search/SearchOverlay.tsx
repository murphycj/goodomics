import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Search, Sparkles, X } from "lucide-react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { SearchResult } from "../../api";
import { searchSamples } from "../../api";
import { cn, titleCase } from "../../lib/utils";
import { Button } from "../ui/button";
import { Dialog, DialogClose, DialogContent, DialogTitle } from "../ui/dialog";
import { useSearchStore } from "./searchStore";

const ENTITY_LABELS: Record<string, string> = {
  sample: "Samples",
  run: "Runs",
};

/** Global command-style search overlay for samples, runs, and Ask AI entry. */
export function SearchOverlay({
  defaultProjectId,
  defaultProjectName,
  draft,
  onClose,
  open,
}: {
  defaultProjectId?: string;
  defaultProjectName?: string;
  draft: string;
  onClose: () => void;
  open: boolean;
}) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);
  const [projectScopeEnabled, setProjectScopeEnabled] = useState(false);
  const [selectedKind, setSelectedKind] = useState("all");
  const inputRef = useRef<HTMLInputElement | null>(null);
  const navigate = useNavigate();
  const openAsk = useSearchStore((state) => state.openAsk);

  const effectiveProjectId = projectScopeEnabled ? defaultProjectId : undefined;
  const results = useQuery({
    queryKey: ["search", effectiveProjectId ?? "global", query],
    queryFn: () => searchSamples({ projectId: effectiveProjectId, query }),
    enabled: open && query.trim().length > 0,
  });

  const items = results.data ?? [];
  const countsByKind = useMemo(() => {
    return items.reduce<Record<string, number>>((counts, item) => {
      counts[item.kind] = (counts[item.kind] ?? 0) + 1;
      return counts;
    }, {});
  }, [items]);
  const filters = useMemo(() => {
    const kinds = Object.keys(countsByKind).sort((left, right) => {
      const preferredOrder = ["sample", "run"];
      const leftIndex = preferredOrder.indexOf(left);
      const rightIndex = preferredOrder.indexOf(right);
      if (leftIndex !== -1 || rightIndex !== -1) {
        return (
          (leftIndex === -1 ? preferredOrder.length : leftIndex) -
          (rightIndex === -1 ? preferredOrder.length : rightIndex)
        );
      }
      return left.localeCompare(right);
    });
    return [
      { kind: "all", label: "All", count: items.length },
      ...kinds.map((kind) => ({
        kind,
        label: ENTITY_LABELS[kind] ?? `${titleCase(kind)}s`,
        count: countsByKind[kind],
      })),
    ];
  }, [countsByKind, items.length]);
  const filteredItems =
    selectedKind === "all"
      ? items
      : items.filter((item) => item.kind === selectedKind);
  const showAskTool = isAskRelevant(query);
  const selectableCount = (showAskTool ? 1 : 0) + filteredItems.length;

  useEffect(() => {
    if (open) {
      setProjectScopeEnabled(Boolean(defaultProjectId));
      setQuery(draft);
      setTimeout(() => inputRef.current?.focus(), 0);
    } else {
      setQuery("");
      setProjectScopeEnabled(Boolean(defaultProjectId));
      setSelectedKind("all");
    }
  }, [defaultProjectId, draft, open]);

  useEffect(() => {
    setActiveIndex(-1);
  }, [effectiveProjectId, query, selectedKind]);

  useEffect(() => {
    if (selectedKind !== "all" && (countsByKind[selectedKind] ?? 0) === 0) {
      setSelectedKind("all");
    }
  }, [countsByKind, selectedKind]);

  useEffect(() => {
    if (activeIndex >= selectableCount) {
      setActiveIndex(selectableCount > 0 ? selectableCount - 1 : -1);
    }
  }, [activeIndex, selectableCount]);

  const openResult = (result: SearchResult | undefined) => {
    if (!result?.project_id) return;
    if (result.kind === "run" && result.run_id) {
      onClose();
      void navigate({
        to: "/project/$projectId/runs/$runId",
        params: { projectId: result.project_id, runId: result.run_id },
      });
      return;
    }
    if (result.kind === "sample" && result.sample_id) {
      onClose();
      void navigate({
        to: "/project/$projectId/samples/$sampleId",
        params: { projectId: result.project_id, sampleId: result.sample_id },
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && onClose()}>
      <DialogContent
        className="top-[15vh] h-[560px] w-[680px] max-w-[calc(100vw-2rem)] translate-y-0 gap-0 overflow-hidden border-[#3a3a3a] bg-[#242424] p-0 text-[#f3f3f3] shadow-[0_28px_80px_rgb(0_0_0/0.30)]"
        overlayClassName="backdrop-blur-[4px]"
        showCloseButton={false}
      >
        <DialogTitle className="sr-only">Search samples or runs</DialogTitle>
        <SearchPanel
          activeIndex={activeIndex}
          defaultProjectId={defaultProjectId}
          defaultProjectName={defaultProjectName}
          filteredItems={filteredItems}
          filters={filters}
          inputRef={inputRef}
          items={items}
          onAskSelect={() => openAsk(query)}
          onClose={onClose}
          onProjectScopeChange={() => setProjectScopeEnabled((value) => !value)}
          onQueryChange={setQuery}
          onResultOpen={openResult}
          onSelectedKindChange={setSelectedKind}
          projectScopeEnabled={projectScopeEnabled}
          query={query}
          resultsError={results.error instanceof Error ? results.error.message : null}
          resultsLoading={results.isLoading}
          selectedKind={selectedKind}
          setActiveIndex={setActiveIndex}
          showAskTool={showAskTool}
        />
      </DialogContent>
    </Dialog>
  );
}

/** Search dialog body with filters, keyboard navigation, and result rendering. */
function SearchPanel({
  activeIndex,
  defaultProjectId,
  defaultProjectName,
  filteredItems,
  filters,
  inputRef,
  items,
  onAskSelect,
  onClose,
  onProjectScopeChange,
  onQueryChange,
  onResultOpen,
  onSelectedKindChange,
  projectScopeEnabled,
  query,
  resultsError,
  resultsLoading,
  selectedKind,
  setActiveIndex,
  showAskTool,
}: {
  activeIndex: number;
  defaultProjectId?: string;
  defaultProjectName?: string;
  filteredItems: SearchResult[];
  filters: Array<{ kind: string; label: string; count: number }>;
  inputRef: RefObject<HTMLInputElement | null>;
  items: SearchResult[];
  onAskSelect: () => void;
  onClose: () => void;
  onProjectScopeChange: () => void;
  onQueryChange: (query: string) => void;
  onResultOpen: (result: SearchResult | undefined) => void;
  onSelectedKindChange: (kind: string) => void;
  projectScopeEnabled: boolean;
  query: string;
  resultsError: string | null;
  resultsLoading: boolean;
  selectedKind: string;
  setActiveIndex: Dispatch<SetStateAction<number>>;
  showAskTool: boolean;
}) {
  const toolCount = showAskTool ? 1 : 0;
  const selectableCount = toolCount + filteredItems.length;
  const openActiveItem = () => {
    if (activeIndex < 0) return;
    if (showAskTool && activeIndex === 0) {
      onAskSelect();
      return;
    }
    onResultOpen(filteredItems[activeIndex - toolCount]);
  };

  return (
    <>
      <div className="flex h-[58px] items-center gap-3 border-b border-[#353535] px-4">
        <Search size={18} className="shrink-0" />
        <input
          ref={inputRef}
          className="flex-1 border-0 bg-transparent text-[#f3f3f3] outline-none placeholder:text-[#aeb4bd]"
          onChange={(event) => onQueryChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") onClose();
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActiveIndex((index) => {
                if (selectableCount === 0) return -1;
                return Math.min(index + 1, selectableCount - 1);
              });
            }
            if (event.key === "ArrowUp") {
              event.preventDefault();
              setActiveIndex((index) => {
                if (selectableCount === 0) return -1;
                if (index < 0) return selectableCount - 1;
                return Math.max(index - 1, 0);
              });
            }
            if (event.key === "Enter") {
              event.preventDefault();
              openActiveItem();
            }
          }}
          placeholder="Search samples, runs, or tools..."
          value={query}
        />
        <DialogClose asChild>
          <Button
            aria-label="Close search"
            className="border-[#444444] bg-[#2d2d2d] text-[#cfcfcf] hover:border-[#565656] hover:bg-[#333333] hover:text-white"
            size="icon"
            type="button"
            variant="outline"
          >
            <X size={16} />
          </Button>
        </DialogClose>
      </div>
      <div
        className="flex h-[50px] items-center gap-2 overflow-x-auto border-b border-[#353535] px-3"
        aria-label="Search result filters"
      >
        {defaultProjectId && (
          <button
            className={cn(
              "h-[30px] shrink-0 cursor-pointer rounded-full border px-3 text-[0.82rem] transition-colors",
              projectScopeEnabled
                ? "border-[#58c98a] bg-[#e8f8ef] text-[#102017]"
                : "border-[#434343] bg-[#2c2c2c] text-[#c5cbd3] hover:border-[#58c98a] hover:bg-[#e8f8ef] hover:text-[#102017]",
            )}
            onClick={onProjectScopeChange}
            type="button"
          >
            {projectScopeEnabled
              ? defaultProjectName || "This project"
              : "All projects"}
          </button>
        )}
        {query.trim() &&
          items.length > 0 &&
          filters.map((filter) => (
            <button
              className={cn(
                "h-[30px] shrink-0 cursor-pointer rounded-full border border-[#434343] bg-[#2c2c2c] px-3 text-[0.82rem] text-[#c5cbd3] transition-colors",
                "hover:border-[#58c98a] hover:bg-[#e8f8ef] hover:text-[#102017]",
                selectedKind === filter.kind &&
                  "border-[#58c98a] bg-[#e8f8ef] text-[#102017]",
              )}
              key={filter.kind}
              onClick={() => onSelectedKindChange(filter.kind)}
              type="button"
            >
              {filter.label} ({filter.count})
            </button>
          ))}
      </div>
      <div className="h-[452px] overflow-auto p-2.5">
        {showAskTool && (
          <div className="mb-3">
            <div className="px-3 py-2 text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#7f858d]">
              Tools
            </div>
            <button
              className={cn(
                "grid w-full cursor-pointer grid-cols-[28px_1fr] gap-3 rounded-[7px] border-0 bg-transparent px-3 py-3 text-left text-[#f3f3f3] transition-colors",
                activeIndex === 0 ? "bg-[#303030]" : "hover:bg-[#303030]",
              )}
              onClick={onAskSelect}
              onMouseEnter={() => setActiveIndex(0)}
              type="button"
            >
              <span className="flex h-7 w-7 items-center justify-center rounded-md bg-[#e8f8ef] text-[#102017]">
                <Sparkles size={15} />
              </span>
              <span className="grid gap-1">
                <strong>Ask AI</strong>
                <small className="text-xs text-[#aeb4bd]">
                  Ask a natural language question about Goodomics data.
                </small>
              </span>
            </button>
          </div>
        )}
        {!query.trim() && !showAskTool && (
          <div className="p-4 text-[#aeb4bd]">Start typing a sample or run name.</div>
        )}
        {query.trim() && resultsLoading && (
          <div className="p-4 text-[#aeb4bd]">Searching...</div>
        )}
        {query.trim() && resultsError && (
          <div className="p-4 text-[#ffb4a8]">{resultsError}</div>
        )}
        {query.trim() && items.length === 0 && !resultsLoading && (
          <div className="p-4 text-[#aeb4bd]">No samples or runs found.</div>
        )}
        {filteredItems.map((result, index) => (
          <SearchResultRow
            active={index + toolCount === activeIndex}
            key={`${result.project_id}-${result.kind}-${result.run_id ?? result.sample_id}`}
            onClick={() => onResultOpen(result)}
            onMouseEnter={() => setActiveIndex(index + toolCount)}
            result={result}
          />
        ))}
      </div>
    </>
  );
}

/** Clickable search result row for a sample or run. */
function SearchResultRow({
  active,
  onClick,
  onMouseEnter,
  result,
}: {
  active: boolean;
  onClick: () => void;
  onMouseEnter: () => void;
  result: SearchResult;
}) {
  const label =
    result.kind === "run"
      ? result.run_id
      : (result.sample_name ?? result.sample_id);
  const detail = result.kind === "run" ? result.project_name : result.sample_id;
  return (
    <button
      className={cn(
        "grid w-full cursor-pointer gap-1 rounded-[7px] border-0 bg-transparent px-3 py-3 text-left text-[#f3f3f3] transition-colors",
        active ? "bg-[#303030]" : "hover:bg-[#303030]",
      )}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      type="button"
    >
      <span className="text-xs text-[#aeb4bd]">{titleCase(result.kind)}</span>
      <strong>{label}</strong>
      <small className="text-xs text-[#aeb4bd]">
        {detail}
        {result.kind === "sample" && result.project_name
          ? ` · ${result.project_name}`
          : ""}
      </small>
    </button>
  );
}

function isAskRelevant(query: string) {
  const term = query.trim().toLowerCase();
  if (!term) return true;
  return [
    "ai",
    "ask",
    "chat",
    "what",
    "which",
    "show",
    "list",
    "find",
    "summarize",
    "compare",
    "why",
    "how",
  ].some((keyword) => term.includes(keyword));
}
