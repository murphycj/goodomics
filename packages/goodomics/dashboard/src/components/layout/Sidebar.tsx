import { Link } from "@tanstack/react-router";
import {
  Database,
  FileCode2,
  FileText,
  FlaskConical,
  Gauge,
  Layers3,
  Settings,
} from "lucide-react";
import { useState } from "react";
import type { SidebarMode } from "../../lib/types";
import { cn } from "../../lib/utils";
import { SidebarModeSelect } from "./SidebarModeSelect";

const navItems = [
  { suffix: "", label: "Runs", icon: FlaskConical },
  { suffix: "/reports", label: "Reports", icon: FileText },
  { suffix: "/templates", label: "Templates", icon: FileCode2 },
  { suffix: "/cohorts", label: "Cohorts", icon: Layers3 },
  { suffix: "/qc-policies", label: "QC policies", icon: Gauge },
  { suffix: "/database", label: "Database", icon: Database },
  { suffix: "/settings", label: "Settings", icon: Settings },
] as const;

export function Sidebar({
  mode,
  onModeChange,
  projectId,
}: {
  mode: SidebarMode;
  onModeChange: (mode: SidebarMode) => void;
  projectId: string;
}) {
  const [controlOpen, setControlOpen] = useState(false);
  const isExpanded = mode === "expanded";
  const shouldHoldHoverOpen = mode === "hover" && controlOpen;
  const isVisuallyExpanded = isExpanded || shouldHoldHoverOpen;

  return (
    <aside
      className={cn(
        "fixed bottom-0 left-0 top-12 z-20 hidden flex-col justify-between overflow-visible border-r border-[#2a2a2a] bg-[#151515] p-[0.65rem_0.45rem] text-[#f6f6f6] transition-[width] duration-[170ms] md:flex",
        isVisuallyExpanded ? "w-[232px]" : "w-[58px]",
        mode === "hover" &&
          !shouldHoldHoverOpen &&
          "group/sidebar hover:w-[232px]",
      )}
    >
      <nav className="grid gap-1">
        {navItems.map(({ suffix, label, icon: Icon }) => {
          const to = `/project/${projectId}${suffix}`;
          return (
            <Link
              activeProps={{ className: "!bg-[#2b2b2b] !text-white" }}
              className="flex h-[38px] w-full min-w-0 cursor-pointer items-center gap-3 rounded-[7px] border-0 bg-transparent px-[0.72rem] text-[#b7bdc5] no-underline transition-colors hover:bg-[#2b2b2b] hover:text-white"
              key={label}
              title={label}
              to={to}
            >
              <Icon className="h-[18px] w-[18px] shrink-0" />
              <span
                className={cn(
                  "max-w-0 overflow-hidden text-ellipsis whitespace-nowrap opacity-0 transition-[opacity,max-width] duration-[170ms]",
                  isVisuallyExpanded && "max-w-[150px] opacity-100",
                  mode === "hover" &&
                    !shouldHoldHoverOpen &&
                    "group-hover/sidebar:max-w-[150px] group-hover/sidebar:opacity-100",
                )}
              >
                {label}
              </span>
            </Link>
          );
        })}
      </nav>
      <SidebarModeSelect
        expanded={isVisuallyExpanded}
        hoverModeHeldOpen={shouldHoldHoverOpen}
        mode={mode}
        onModeChange={onModeChange}
        onOpenChange={setControlOpen}
      />
    </aside>
  );
}
