import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { SearchResult } from "../../api";
import { searchSamples } from "../../api";
import { cn, titleCase } from "../../lib/utils";
import { Button } from "../ui/button";

const ENTITY_LABELS: Record<string, string> = {
  run: "Runs",
  sample: "Samples",
};

export function SearchOverlay({
  onClose,
  open,
  projectId,
}: {
  onClose: () => void;
  open: boolean;
  projectId?: string;
}) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [selectedKind, setSelectedKind] = useState("all");
  const inputRef = useRef<HTMLInputElement | null>(null);
  const navigate = useNavigate();
  const results = useQuery({
    queryKey: ["search", projectId ?? "global", query],
    queryFn: () => searchSamples({ projectId, query }),
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
      const preferredOrder = ["run", "sample"];
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

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 0);
    } else {
      setQuery("");
      setSelectedKind("all");
    }
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query, projectId, selectedKind]);

  useEffect(() => {
    if (selectedKind !== "all" && (countsByKind[selectedKind] ?? 0) === 0) {
      setSelectedKind("all");
    }
  }, [countsByKind, selectedKind]);

  useEffect(() => {
    if (activeIndex >= filteredItems.length) {
      setActiveIndex(Math.max(filteredItems.length - 1, 0));
    }
  }, [activeIndex, filteredItems.length]);

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

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-start justify-center bg-black/42 px-4 pt-[15vh] backdrop-blur-[4px]"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="h-[520px] w-[620px] max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border border-[#3a3a3a] bg-[#242424] text-[#f3f3f3] shadow-[0_28px_80px_rgb(0_0_0/0.30)]"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="flex h-[58px] items-center gap-3 border-b border-[#353535] px-4">
          <Search size={18} className="shrink-0" />
          <input
            ref={inputRef}
            className="flex-1 border-0 bg-transparent text-[#f3f3f3] outline-none placeholder:text-[#aeb4bd]"
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") onClose();
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setActiveIndex((index) =>
                  Math.min(index + 1, Math.max(filteredItems.length - 1, 0)),
                );
              }
              if (event.key === "ArrowUp") {
                event.preventDefault();
                setActiveIndex((index) => Math.max(index - 1, 0));
              }
              if (event.key === "Enter") {
                event.preventDefault();
                openResult(filteredItems[activeIndex]);
              }
            }}
            placeholder="Search runs or samples..."
            value={query}
          />
          <Button
            className="border-[#444444] bg-[#2d2d2d] text-[#cfcfcf] hover:border-[#565656] hover:bg-[#333333] hover:text-white"
            onClick={onClose}
            size="icon"
            type="button"
            variant="outline"
          >
            <X size={16} />
          </Button>
        </div>
        <div
          className="flex h-[50px] items-center gap-2 overflow-x-auto border-b border-[#353535] px-3"
          aria-label="Search result filters"
        >
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
                onClick={() => setSelectedKind(filter.kind)}
                type="button"
              >
                {filter.label} ({filter.count})
              </button>
            ))}
        </div>
        <div className="h-[412px] overflow-auto p-2.5">
          {!query.trim() && (
            <div className="p-4 text-[#aeb4bd]">
              Start typing a run or sample name.
            </div>
          )}
          {query.trim() && results.isLoading && (
            <div className="p-4 text-[#aeb4bd]">Searching...</div>
          )}
          {query.trim() && results.error && (
            <div className="p-4 text-[#b42318]">{results.error.message}</div>
          )}
          {query.trim() && results.data?.length === 0 && (
            <div className="p-4 text-[#aeb4bd]">No runs or samples found.</div>
          )}
          {filteredItems.map((result, index) => (
            <SearchResultRow
              active={index === activeIndex}
              key={`${result.project_id}-${result.kind}-${result.run_id ?? result.sample_id}`}
              onClick={() => openResult(result)}
              result={result}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function SearchResultRow({
  active,
  onClick,
  result,
}: {
  active: boolean;
  onClick: () => void;
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
