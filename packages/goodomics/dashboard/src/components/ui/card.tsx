import * as React from "react";
import { cn } from "../../lib/utils";

/** Generic bordered card container for grouped dashboard content. */
const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "mt-4 rounded-lg border border-[#dce3eb] bg-white p-4 shadow-[0_14px_34px_rgb(25_32_43/0.05)]",
        className,
      )}
      {...props}
    />
  ),
);
Card.displayName = "Card";

/** Card header layout for titles and actions. */
const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn("mb-3 flex items-start justify-between gap-4", className)}
    {...props}
  />
));
CardHeader.displayName = "CardHeader";

/** Card title typography primitive. */
const CardTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3 ref={ref} className={cn("m-0 text-base font-semibold", className)} {...props} />
));
CardTitle.displayName = "CardTitle";

/** Card body wrapper used when padding or layout differs per view. */
const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("", className)} {...props} />
));
CardContent.displayName = "CardContent";

export { Card, CardContent, CardHeader, CardTitle };
