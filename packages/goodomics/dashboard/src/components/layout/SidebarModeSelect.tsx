import { PanelLeft } from "lucide-react";
import type { SidebarMode } from "../../lib/types";
import { cn } from "../../lib/utils";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "../ui/select";

const sidebarModeOptions = [
  { value: "expanded", label: "Expanded" },
  { value: "collapsed", label: "Collapsed" },
  { value: "hover", label: "Expand on hover" },
] as const satisfies ReadonlyArray<{ value: SidebarMode; label: string }>;

/** Sidebar display mode picker shown at the bottom of project navigation. */
export function SidebarModeSelect({
  expanded,
  hoverModeHeldOpen,
  mode,
  onModeChange,
  onOpenChange,
}: {
  expanded: boolean;
  hoverModeHeldOpen: boolean;
  mode: SidebarMode;
  onModeChange: (mode: SidebarMode) => void;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Select
      onOpenChange={onOpenChange}
      onValueChange={(value) => onModeChange(value as SidebarMode)}
      value={mode}
    >
      <SelectTrigger
        aria-label="Sidebar control"
        className={cn(
          "h-[38px] min-w-0 justify-start gap-3 rounded-[7px] border-0 bg-transparent px-[0.72rem] py-0 text-[#b7bdc5] shadow-none transition-colors hover:bg-[#2b2b2b] hover:text-white focus:ring-0 [&>svg:last-child]:ml-auto [&>svg:last-child]:hidden",
          expanded && "[&>svg:last-child]:block",
          mode === "hover" &&
            !hoverModeHeldOpen &&
            "group-hover/sidebar:[&>svg:last-child]:block",
        )}
        title="Sidebar control"
      >
        <PanelLeft className="h-[18px] w-[18px] shrink-0" />
        <span
          className={cn(
            "max-w-0 overflow-hidden text-ellipsis whitespace-nowrap opacity-0 transition-[opacity,max-width] duration-[170ms]",
            expanded && "max-w-[150px] opacity-100",
            mode === "hover" &&
              !hoverModeHeldOpen &&
              "group-hover/sidebar:max-w-[150px] group-hover/sidebar:opacity-100",
          )}
        >
          <SelectValue />
        </span>
      </SelectTrigger>
      <SelectContent
        align="end"
        className="min-w-[230px] border-[#3a3a3a] bg-[#232323] text-[#d6d6d6] shadow-[0_18px_42px_rgb(0_0_0/0.28)]"
        position="popper"
        side="right"
        sideOffset={8}
      >
        <SelectGroup>
          <SelectLabel className="border-b border-[#383838] px-2 pb-2.5 pt-1 text-[0.85rem] normal-case text-[#9f9f9f]">
            Sidebar control
          </SelectLabel>
          {sidebarModeOptions.map((item) => (
            <SelectItem
              className="text-[#d6d6d6] focus:bg-[#303030] focus:text-white data-[state=checked]:bg-[#303030] data-[state=checked]:text-white"
              key={item.value}
              value={item.value}
            >
              {item.label}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  );
}
