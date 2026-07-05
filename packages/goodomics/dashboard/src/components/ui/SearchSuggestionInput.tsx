import { Search } from "lucide-react";
import type React from "react";
import { useEffect, useRef, useState } from "react";

export type SearchSuggestionOption = {
  id: string;
  label: string;
  subtitle?: string;
};

export function SearchSuggestionInput({
  emptyText = "No matches found.",
  hasMore = false,
  inputValue,
  isLoading = false,
  loadMoreText = "Loading more...",
  options,
  placeholder,
  searchValue,
  onInputValueChange,
  onLoadMore,
  onOpenChange,
  onSearchValueChange,
  onSelect,
}: {
  emptyText?: string;
  hasMore?: boolean;
  inputValue: string;
  isLoading?: boolean;
  loadMoreText?: string;
  options: SearchSuggestionOption[];
  placeholder?: string;
  searchValue: string;
  onInputValueChange?: (value: string) => void;
  onLoadMore?: () => void;
  onOpenChange?: (open: boolean) => void;
  onSearchValueChange: (value: string) => void;
  onSelect: (option: SearchSuggestionOption) => void;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const setOpenState = (nextOpen: boolean) => {
    setOpen(nextOpen);
    onOpenChange?.(nextOpen);
  };

  useEffect(() => {
    setActiveIndex(0);
  }, [searchValue]);

  useEffect(() => {
    if (options.length === 0) {
      setActiveIndex(0);
      return;
    }
    setActiveIndex((current) => Math.min(current, options.length - 1));
  }, [options.length]);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpenState(false);
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const activeOptionId = optionDomId(options[activeIndex]?.id);
    if (!activeOptionId) return;
    document
      .getElementById(activeOptionId)
      ?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, open, options]);

  const chooseOption = (option: SearchSuggestionOption) => {
    onSelect(option);
    setOpenState(false);
  };

  const handleScroll = () => {
    const list = listRef.current;
    if (!list || !hasMore || isLoading) return;
    const remaining = list.scrollHeight - list.scrollTop - list.clientHeight;
    if (remaining < 48) onLoadMore?.();
  };

  return (
    <div className="relative" ref={rootRef}>
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#758195]" />
        <input
          aria-autocomplete="list"
          aria-expanded={open}
          className="flex h-10 w-full rounded-md border border-[#d6dee8] bg-white px-3 py-2 pl-9 text-sm text-[#1f2937] outline-none transition-colors placeholder:text-[#9ca3af] focus:border-[#16784a] focus:ring-2 focus:ring-[#16784a]/15"
          placeholder={placeholder}
          role="combobox"
          value={inputValue}
          onChange={(event) => {
            onInputValueChange?.(event.target.value);
            onSearchValueChange(event.target.value);
            setOpenState(true);
          }}
          onFocus={() => setOpenState(true)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setOpenState(true);
              if (options.length > 0) {
                setActiveIndex((current) =>
                  current + 1 >= options.length ? 0 : current + 1,
                );
              }
              return;
            }
            if (event.key === "ArrowUp") {
              event.preventDefault();
              setOpenState(true);
              if (options.length > 0) {
                setActiveIndex((current) =>
                  current - 1 < 0 ? options.length - 1 : current - 1,
                );
              }
              return;
            }
            if (event.key === "Enter") {
              const option = options[activeIndex];
              if (!open || !option) return;
              event.preventDefault();
              chooseOption(option);
              return;
            }
            if (event.key === "Escape") {
              setOpenState(false);
            }
          }}
        />
      </div>
      {open ? (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 rounded-md border border-[#d6dee8] bg-white py-1 shadow-[0_12px_30px_rgb(0_0_0/0.14)]">
          <div
            className="max-h-64 overflow-y-auto px-1"
            ref={listRef}
            role="listbox"
            onScroll={handleScroll}
          >
            {options.map((option, index) => {
              const active = index === activeIndex;
              return (
                <button
                  className={[
                    "grid w-full gap-0.5 rounded px-2 py-2 text-left text-sm transition-colors",
                    active ? "bg-[#f4f8fb]" : "hover:bg-[#f8fafc]",
                  ].join(" ")}
                  id={optionDomId(option.id)}
                  key={option.id}
                  aria-selected={active}
                  role="option"
                  type="button"
                  onClick={() => chooseOption(option)}
                  onMouseEnter={() => setActiveIndex(index)}
                >
                  <span className="truncate font-semibold text-[#1f2937]">
                    {highlightSearchMatch(option.label, searchValue)}
                  </span>
                  {option.subtitle ? (
                    <span className="truncate text-xs text-[#657082]">
                      {highlightSearchMatch(option.subtitle, searchValue)}
                    </span>
                  ) : null}
                </button>
              );
            })}
            {options.length === 0 && !isLoading ? (
              <div className="px-3 py-4 text-sm text-[#657082]">{emptyText}</div>
            ) : null}
            {isLoading ? (
              <div className="px-3 py-2 text-xs text-[#657082]">
                {loadMoreText}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function optionDomId(optionId: string | undefined) {
  return optionId
    ? `search-suggestion-${optionId.replace(/[^a-zA-Z0-9_-]/g, "_")}`
    : undefined;
}

function highlightSearchMatch(text: string, search: string) {
  const query = search.trim();
  if (!query) return text;
  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  let matchIndex = lowerText.indexOf(lowerQuery, cursor);
  while (matchIndex >= 0) {
    if (matchIndex > cursor) parts.push(text.slice(cursor, matchIndex));
    const end = matchIndex + query.length;
    parts.push(
      <mark
        className="rounded-sm bg-[#dff4e8] px-0.5 text-inherit"
        key={`${matchIndex}-${end}`}
      >
        {text.slice(matchIndex, end)}
      </mark>,
    );
    cursor = end;
    matchIndex = lowerText.indexOf(lowerQuery, cursor);
  }
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts.length ? parts : text;
}
