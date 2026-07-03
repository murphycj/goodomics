import { Columns3 } from "lucide-react";
import { Button } from "./button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./dropdown-menu";

export type ColumnVisibilityOption = string | { key: string; label: string };

/** Dropdown control for hiding and showing table/grid columns. */
export function ColumnVisibilityMenu({
  columns,
  hiddenColumns,
  onChange,
}: {
  columns: ColumnVisibilityOption[];
  hiddenColumns: Set<string>;
  onChange: (columns: Set<string>) => void;
}) {
  const options = columns.map((column) =>
    typeof column === "string" ? { key: column, label: column } : column,
  );
  const visibleCount = columns.length - hiddenColumns.size;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          title="Columns"
          aria-label="Columns"
        >
          <Columns3 className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-[420px] overflow-auto">
        <DropdownMenuLabel>Visible columns</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {options.map((column) => {
          const checked = !hiddenColumns.has(column.key);
          return (
            <DropdownMenuItem
              key={column.key}
              onSelect={(event) => {
                event.preventDefault();
                if (checked && visibleCount <= 1) return;
                const next = new Set(hiddenColumns);
                if (checked) {
                  next.add(column.key);
                } else {
                  next.delete(column.key);
                }
                onChange(next);
              }}
            >
              <input
                type="checkbox"
                checked={checked}
                readOnly
                className="h-4 w-4 accent-[#16784a]"
              />
              <span className="truncate">{column.label}</span>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
