import { type RefObject } from "react";
import { X } from "lucide-react";
import { cn } from "../../lib/utils";
import { isRecord } from "../../lib/valueUtils";

export type CellPreview = {
  column: string;
  rowNumber?: number;
  tableName: string;
  value: unknown;
};

/** Data grid cell renderer that keeps structured payloads compact. */
export function CellValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="block w-full truncate text-left text-[#9aa5b5]">NULL</span>;
  }
  if (typeof value === "boolean") {
    return (
      <span className="block w-full truncate text-left">
        {value ? "TRUE" : "FALSE"}
      </span>
    );
  }
  if (typeof value === "object") {
    return (
      <span
        className="inline-block max-w-full truncate rounded bg-[#eef3f7] px-2 py-0.5 text-left text-xs text-[#526071]"
        title={JSON.stringify(value)}
      >
        {payloadSummary(value)}
      </span>
    );
  }
  return <span className="block w-full truncate text-left">{String(value)}</span>;
}

/** Slide-out panel for inspecting a full table cell value. */
export function CellPreviewPanel({
  isOpen,
  onClosed,
  panelRef,
  preview,
  onClose,
}: {
  isOpen: boolean;
  onClosed: () => void;
  panelRef: RefObject<HTMLElement | null>;
  preview: CellPreview;
  onClose: () => void;
}) {
  const formattedValue = formatPreviewValue(preview.value);
  const lines = formattedValue.split("\n");
  return (
    <aside
      ref={panelRef}
      className={cn(
        "database-cell-preview-panel",
        isOpen
          ? "database-cell-preview-panel-open"
          : "database-cell-preview-panel-closed",
      )}
      onTransitionEnd={(event) => {
        if (event.propertyName === "width" && !isOpen) {
          onClosed();
        }
      }}
    >
      <div className="database-cell-preview-panel-inner">
        <div className="flex min-h-[48px] items-center justify-between gap-3 border-b border-[#dce3eb] px-4">
          <div className="min-w-0">
            <p className="m-0 truncate text-sm font-semibold text-[#1d2430]">
              Viewing value of: {preview.column}
            </p>
            <p className="m-0 mt-0.5 truncate text-xs text-[#657082]">
              {preview.tableName}
              {preview.rowNumber ? ` · row ${preview.rowNumber.toLocaleString()}` : ""}
            </p>
          </div>
          <button
            aria-label="Close value preview"
            className="inline-flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-md border border-[#dce3eb] bg-white text-[#657082] transition-colors hover:border-[#8edeb4] hover:bg-[#eef8f2] hover:text-[#16784a] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#21a66a]"
            onClick={onClose}
            type="button"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-[#1f2329] py-3">
          <div className="font-mono text-xs leading-5">
            {lines.map((line, index) => (
              <div
                className="grid grid-cols-[3rem_minmax(0,1fr)] px-3"
                key={`${index}:${line}`}
              >
                <span className="select-none pr-4 text-right text-[#7a8798]">
                  {index + 1}
                </span>
                <pre className="m-0 whitespace-pre-wrap break-words text-[#eef2f6]">
                  {line || " "}
                </pre>
              </div>
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
}

export function payloadSummary(value: unknown) {
  if (Array.isArray(value)) return `${value.length.toLocaleString()} values`;
  if (isRecord(value)) {
    const rows = Array.isArray(value.rows) ? value.rows.length : null;
    const columns = Array.isArray(value.columns) ? value.columns.length : null;
    if (rows !== null && columns !== null) {
      return `${rows.toLocaleString()} rows x ${columns.toLocaleString()} columns`;
    }
    return `${Object.keys(value).length.toLocaleString()} keys`;
  }
  return "Payload";
}

export function formatPreviewValue(value: unknown) {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}
