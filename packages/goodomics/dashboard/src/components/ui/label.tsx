import * as LabelPrimitive from "@radix-ui/react-label";
import * as React from "react";
import { cn } from "../../lib/utils";

/** Form label primitive with compact dashboard typography. */
export const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn("text-xs font-bold text-[#596678] uppercase", className)}
    {...props}
  />
));
Label.displayName = LabelPrimitive.Root.displayName;
