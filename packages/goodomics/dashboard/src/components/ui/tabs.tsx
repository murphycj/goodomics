import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as React from "react";
import { cn } from "../../lib/utils";

/** Radix tabs root re-export for dashboard tabbed content. */
const Tabs = TabsPrimitive.Root;

/** Horizontal tab list with Goodomics bottom-border styling. */
const TabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn("mb-4 flex gap-1 border-b border-[#dce3eb]", className)}
    {...props}
  />
));
TabsList.displayName = TabsPrimitive.List.displayName;

/** Clickable tab trigger with active underline styling. */
const TabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "inline-flex cursor-pointer items-center justify-center border-0 border-b-[3px] border-transparent bg-transparent px-4 py-3 text-sm text-[#596678] transition-colors",
      "data-[state=active]:border-[#16784a] data-[state=active]:text-[#1d2430] data-[state=active]:font-bold",
      "hover:text-[#1d2430]",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = TabsPrimitive.Trigger.displayName;

/** Tab content panel with neutral spacing defaults. */
const TabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content ref={ref} className={cn("mt-0", className)} {...props} />
));
TabsContent.displayName = TabsPrimitive.Content.displayName;

export { Tabs, TabsContent, TabsList, TabsTrigger };
