import { useEffect, useRef } from "react";
import { cn } from "../../lib/utils";

/** Native checkbox with support for an accessible indeterminate state. */
export function SelectionCheckbox({
  checked,
  className,
  indeterminate = false,
  ...props
}: Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> & {
  indeterminate?: boolean;
}) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <input
      {...props}
      ref={ref}
      checked={checked}
      className={cn(
        "h-4 w-4 cursor-pointer rounded border-[#b8c3d1] accent-[#16784a] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#16784a]/30",
        className,
      )}
      type="checkbox"
    />
  );
}
