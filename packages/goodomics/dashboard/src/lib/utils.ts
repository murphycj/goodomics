import type { AnalyticsMetric } from "../api";

export function projectIdFromPath(pathname: string) {
  return pathname.match(/^\/project\/([^/]+)/)?.[1] ?? null;
}

export function formatDate(value: string) {
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
  return typeof metric.value === "number"
    ? metric.value.toLocaleString()
    : metric.value;
}

export function shortPath(path: string) {
  const parts = path.split("/");
  return parts.length > 4 ? `.../${parts.slice(-4).join("/")}` : path;
}

export function titleCase(value: string) {
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}
