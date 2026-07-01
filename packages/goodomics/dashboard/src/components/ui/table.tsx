import * as React from "react";
import { cn } from "../../lib/utils";

/** Scrollable table frame with Goodomics border and shadow styling. */
const TableWrap = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "mt-4 overflow-auto rounded-lg border border-[#dce3eb] bg-white shadow-[0_14px_34px_rgb(25_32_43/0.05)]",
        className,
      )}
      {...props}
    />
  ),
);
TableWrap.displayName = "TableWrap";

/** Base table element with a stable minimum width for data-heavy views. */
const Table = React.forwardRef<
  HTMLTableElement,
  React.TableHTMLAttributes<HTMLTableElement>
>(({ className, ...props }, ref) => (
  <table
    ref={ref}
    className={cn("w-full min-w-[760px] border-collapse", className)}
    {...props}
  />
));
Table.displayName = "Table";

/** Table header section primitive. */
const TableHeader = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <thead ref={ref} className={cn("", className)} {...props} />
));
TableHeader.displayName = "TableHeader";

/** Table body section primitive. */
const TableBody = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tbody ref={ref} className={cn("", className)} {...props} />
));
TableBody.displayName = "TableBody";

/** Table row primitive with hover and divider styling. */
const TableRow = React.forwardRef<
  HTMLTableRowElement,
  React.HTMLAttributes<HTMLTableRowElement>
>(({ className, ...props }, ref) => (
  <tr
    ref={ref}
    className={cn(
      "border-b border-[#e8edf3] transition-colors last:border-b-0 hover:bg-[#f9fbfa]",
      className,
    )}
    {...props}
  />
));
TableRow.displayName = "TableRow";

/** Table column heading primitive. */
const TableHead = React.forwardRef<
  HTMLTableCellElement,
  React.ThHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
  <th
    ref={ref}
    className={cn(
      "border-b border-[#e8edf3] bg-[#f8fafb] px-3 py-2.5 text-left text-xs font-bold uppercase text-[#596678]",
      className,
    )}
    {...props}
  />
));
TableHead.displayName = "TableHead";

/** Table data cell primitive. */
const TableCell = React.forwardRef<
  HTMLTableCellElement,
  React.TdHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
  <td
    ref={ref}
    className={cn("px-3 py-2.5 text-sm align-top text-[#1d2430]", className)}
    {...props}
  />
));
TableCell.displayName = "TableCell";

export { Table, TableBody, TableCell, TableHead, TableHeader, TableRow, TableWrap };
