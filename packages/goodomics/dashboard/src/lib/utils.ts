import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { AnalyticsMetric } from "../api";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function projectIdFromPath(pathname: string) {
  return pathname.match(/^\/project\/([^/]+)/)?.[1] ?? null;
}

/** Formats API timestamps as either full local datetimes or compact table dates. */
export function formatDate(
  value: string,
  options: { style?: "date" | "datetime" } = {},
) {
  if (options.style === "date") {
    return new Date(value).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }
  return new Date(value).toLocaleString();
}

export function formatBytes(value: number) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    units.length - 1,
  );
  return `${(value / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatMetricValue(metric: AnalyticsMetric) {
  if (typeof metric.value === "number") return metric.value.toLocaleString();
  if (metric.value == null) return "—";
  if (typeof metric.value === "object") return JSON.stringify(metric.value);
  return String(metric.value);
}

export function shortPath(path: string) {
  const parts = path.split("/");
  return parts.length > 4 ? `.../${parts.slice(-4).join("/")}` : path;
}

export function titleCase(value: string) {
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}
