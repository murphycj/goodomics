import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "./button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./select";

const DEFAULT_PAGE_SIZE_OPTIONS = [25, 50, 100, 250];

export function PaginationBar({
  className = "",
  isLoading = false,
  itemLabel = "records",
  onPageChange,
  onPageSizeChange,
  pageIndex,
  pageSize,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
  total,
}: {
  className?: string;
  isLoading?: boolean;
  itemLabel?: string;
  onPageChange: (pageIndex: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
  pageIndex: number;
  pageSize: number;
  pageSizeOptions?: number[];
  total: number;
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const pageNumber = Math.min(pageIndex + 1, pageCount);
  const canGoBack = pageIndex > 0 && !isLoading;
  const canGoForward = pageIndex + 1 < pageCount && !isLoading;
  const goToPage = (nextPageNumber: number) => {
    const clampedPage = Math.min(Math.max(nextPageNumber, 1), pageCount);
    onPageChange(clampedPage - 1);
  };

  return (
    <div
      className={`flex min-h-[48px] shrink-0 items-center gap-2.5 border-t border-[#dce3eb] bg-white px-3 py-1.5 text-sm ${className}`}
    >
      <Button
        aria-label="Previous page"
        disabled={!canGoBack}
        onClick={() => onPageChange(Math.max(0, pageIndex - 1))}
        size="icon"
        title="Previous page"
        type="button"
        variant="outline"
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <span className="text-[#657082]">Page</span>
      <input
        aria-label="Current page"
        className="h-8 w-14 rounded-lg border border-[#cfd8e3] bg-white px-2 text-center text-sm font-semibold text-[#1d2430] outline-none focus:border-[#21a66a] focus:ring-2 focus:ring-[#21a66a]/10"
        max={pageCount}
        min={1}
        onChange={(event) => goToPage(Number(event.target.value) || 1)}
        type="number"
        value={pageNumber}
      />
      <span className="text-[#657082]">of {pageCount.toLocaleString()}</span>
      <Button
        aria-label="Next page"
        disabled={!canGoForward}
        onClick={() => onPageChange(Math.min(pageCount - 1, pageIndex + 1))}
        size="icon"
        title="Next page"
        type="button"
        variant="outline"
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
      {onPageSizeChange ? (
        <Select
          value={String(pageSize)}
          onValueChange={(value) => onPageSizeChange(Number(value))}
        >
          <SelectTrigger className="h-8 w-[118px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {pageSizeOptions.map((size) => (
              <SelectItem key={size} value={String(size)}>
                {size} rows
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : null}
      <span className="font-medium text-[#657082]">
        {total.toLocaleString()} {itemLabel}
      </span>
    </div>
  );
}
