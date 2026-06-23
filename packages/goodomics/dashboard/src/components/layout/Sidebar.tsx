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
import { titleCase } from "../../lib/utils";

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
  const sidebarClass =
    mode === "expanded"
      ? "expanded"
      : mode === "collapsed"
        ? "collapsed"
        : "hover";

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
    <aside className={`sidebar ${sidebarClass}`}>
      <nav className="sidebar-nav">
        {navItems.map(({ suffix, label, icon: Icon }) => {
          const to = `/project/${projectId}${suffix}`;
          return (
            <Link
              activeProps={{ className: "active" }}
              className="sidebar-link"
              key={label}
              title={label}
              to={to}
            >
              <Icon size={18} />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="sidebar-footer" ref={controlRef}>
        <button
          className="sidebar-control-button"
          onClick={() => setControlOpen((value) => !value)}
          title="Sidebar control"
          type="button"
        >
          <PanelLeft size={18} />
          <span>Sidebar</span>
        </button>
        {controlOpen && (
          <div className="sidebar-control-menu">
            <div className="sidebar-control-title">Sidebar control</div>
            {(["expanded", "collapsed", "hover"] as const).map((item) => (
              <button
                className={mode === item ? "selected" : ""}
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
