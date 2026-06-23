import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { SearchResult } from "../../api";
import { searchSamples } from "../../api";
import { titleCase } from "../../lib/utils";

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
    <div className="search-backdrop" onClick={onClose} role="presentation">
      <div
        className="search-dialog"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <div className="search-input-row">
          <Search size={18} />
          <input
            ref={inputRef}
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
          <button className="icon-button" onClick={onClose} type="button">
            <X size={16} />
          </button>
        </div>
        <div className="search-filters" aria-label="Search result filters">
          {query.trim() &&
            items.length > 0 &&
            filters.map((filter) => (
              <button
                className={
                  selectedKind === filter.kind
                    ? "search-filter-pill active"
                    : "search-filter-pill"
                }
                key={filter.kind}
                onClick={() => setSelectedKind(filter.kind)}
                type="button"
              >
                {filter.label} ({filter.count})
              </button>
            ))}
        </div>
        <div className="search-results">
          {!query.trim() && (
            <div className="search-empty">
              Start typing a run or sample name.
            </div>
          )}
          {query.trim() && results.isLoading && (
            <div className="search-empty">Searching...</div>
          )}
          {query.trim() && results.error && (
            <div className="search-empty error-text">
              {results.error.message}
            </div>
          )}
          {query.trim() && results.data?.length === 0 && (
            <div className="search-empty">No runs or samples found.</div>
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
      className={active ? "search-result-row active" : "search-result-row"}
      onClick={onClick}
      type="button"
    >
      <span className="search-result-kind">{titleCase(result.kind)}</span>
      <strong>{label}</strong>
      <small>
        {detail}
        {result.kind === "sample" && result.project_name
          ? ` · ${result.project_name}`
          : ""}
      </small>
    </button>
  );
}
