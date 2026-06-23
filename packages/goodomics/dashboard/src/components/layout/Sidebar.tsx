import { Link } from "@tanstack/react-router";
import {
  Circle,
  Database,
  FileCode2,
  FileText,
  FlaskConical,
  Gauge,
  Layers3,
  PanelLeft,
  Settings,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { SidebarMode } from "../../lib/types";
import { cn, titleCase } from "../../lib/utils";

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
  const controlRef = useRef<HTMLDivElement | null>(null);
  const isExpanded = mode === "expanded";

  useEffect(() => {
    if (!controlOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!controlRef.current?.contains(event.target as Node)) {
        setControlOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [controlOpen]);

  return (
    <aside
      className={cn(
        "fixed bottom-0 left-0 top-12 z-20 hidden flex-col justify-between overflow-visible border-r border-[#2a2a2a] bg-[#151515] p-[0.65rem_0.45rem] text-[#f6f6f6] transition-[width] duration-[170ms] md:flex",
        isExpanded ? "w-[232px]" : "w-[58px]",
        mode === "hover" && "group/sidebar hover:w-[232px]",
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
                  isExpanded && "max-w-[150px] opacity-100",
                  mode === "hover" &&
                    "group-hover/sidebar:max-w-[150px] group-hover/sidebar:opacity-100",
                )}
              >
                {label}
              </span>
            </Link>
          );
        })}
      </nav>
      <div className="relative" ref={controlRef}>
        <button
          className="flex h-[38px] w-full min-w-0 cursor-pointer items-center gap-3 rounded-[7px] border-0 bg-transparent px-[0.72rem] text-[#b7bdc5] transition-colors hover:bg-[#2b2b2b] hover:text-white"
          onClick={() => setControlOpen((value) => !value)}
          title="Sidebar control"
          type="button"
        >
          <PanelLeft className="h-[18px] w-[18px] shrink-0" />
          <span
            className={cn(
              "max-w-0 overflow-hidden text-ellipsis whitespace-nowrap opacity-0 transition-[opacity,max-width] duration-[170ms]",
              isExpanded && "max-w-[150px] opacity-100",
              mode === "hover" &&
                "group-hover/sidebar:max-w-[150px] group-hover/sidebar:opacity-100",
            )}
          >
            Sidebar
          </span>
        </button>
        {controlOpen && (
          <div className="absolute bottom-11 left-[0.2rem] z-40 grid min-w-[230px] gap-1 rounded-lg border border-[#3a3a3a] bg-[#232323] p-[0.55rem] text-[#d6d6d6] shadow-[0_18px_42px_rgb(0_0_0/0.28)]">
            <div className="border-b border-[#383838] px-2 pb-2.5 pt-1 text-[0.85rem] text-[#9f9f9f]">
              Sidebar control
            </div>
            {(["expanded", "collapsed", "hover"] as const).map((item) => (
              <button
                className={cn(
                  "flex cursor-pointer items-center gap-3 rounded-md border-0 bg-transparent px-2 py-2 text-left text-[#d6d6d6] transition-colors hover:bg-[#303030] hover:text-white",
                  mode === item && "bg-[#303030] text-white",
                )}
                key={item}
                onClick={() => {
                  onModeChange(item);
                  setControlOpen(false);
                }}
                type="button"
              >
                <Circle size={12} />
                {item === "hover" ? "Expand on hover" : titleCase(item)}
              </button>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
