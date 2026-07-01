import * as React from "react";
import { cn } from "../../lib/utils";

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

/** Goodomics text input primitive with consistent focus and disabled styling. */
export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex min-h-[38px] w-full rounded-lg border border-[#cfd8e3] bg-white px-3 py-1 text-sm outline-none transition-colors",
        "placeholder:text-[#9ca3af]",
        "focus:border-[#21a66a] focus:ring-2 focus:ring-[#21a66a]/10",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
