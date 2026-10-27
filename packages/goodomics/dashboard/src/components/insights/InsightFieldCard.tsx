import { Eye, EyeOff, GripVertical, MoreHorizontal, Trash2 } from "lucide-react";
import type { FieldSelection } from "../../lib/insightSchemas";
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui";
import type { CatalogField } from "./InsightFieldPicker";

export function InsightFieldCard({
  field,
  hidden = false,
  label,
  onDragStart,
  onDrop,
  onRemove,
  onReplace,
  onToggleVisibility,
  readOnly,
}: {
  field?: CatalogField;
  hidden?: boolean;
  label?: string;
  onDragStart?: () => void;
  onDrop?: () => void;
  onRemove?: () => void;
  onReplace?: () => void;
  onToggleVisibility?: () => void;
  readOnly: boolean;
}) {
  return (
    <div
      className={[
        "group flex min-h-12 items-center gap-2 rounded-md border bg-white px-2 py-1.5 shadow-sm transition-colors",
        hidden ? "border-[#e1e6ec] opacity-60" : "border-[#d6dee8] hover:border-[#aebbc8]",
      ].join(" ")}
      draggable={!readOnly && Boolean(onDragStart)}
      onDragOver={(event) => event.preventDefault()}
      onDragStart={onDragStart}
      onDrop={onDrop}
    >
      {onDragStart ? <GripVertical className="h-4 w-4 shrink-0 cursor-grab text-[#a2adba] opacity-0 group-hover:opacity-100" /> : null}
      {onToggleVisibility ? (
        <button
          aria-label={hidden ? "Show field" : "Hide field"}
          className="flex h-8 w-8 shrink-0 items-center justify-center text-[#657082] hover:text-[#253343]"
          disabled={readOnly}
          type="button"
          onClick={onToggleVisibility}
        >
          {hidden ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      ) : null}
      <button className="min-w-0 flex-1 text-left" disabled={readOnly} type="button" onClick={onReplace}>
        <span className="block truncate text-sm font-semibold text-[#1f2937]">{label || field?.display_name || "Choose a field"}</span>
        <span className="block truncate text-xs text-[#758195]">{field ? field.data_contract_id || "Metadata" : "No field selected"}</span>
      </button>
      {!readOnly && (onRemove || onReplace) ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button aria-label="Field actions" size="icon" variant="ghost"><MoreHorizontal className="h-4 w-4" /></Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[180px]">
            {onReplace ? <DropdownMenuItem onClick={onReplace}>Choose another field</DropdownMenuItem> : null}
            {onRemove ? <DropdownMenuSeparator /> : null}
            {onRemove ? <DropdownMenuItem className="text-[#b42318]" onClick={onRemove}><Trash2 className="h-4 w-4" /> Remove</DropdownMenuItem> : null}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
    </div>
  );
}

export function selectedCatalogField(selection: FieldSelection, fields: CatalogField[]) {
  return fields.find((field) => field.field === selection.field);
}
