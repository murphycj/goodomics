export type ProjectRecentKind =
  | "database"
  | "insight"
  | "policies"
  | "report"
  | "run"
  | "runs"
  | "sample"
  | "sample-groups"
  | "samples"
  | "settings";

export type ProjectRecentView = {
  description: string;
  href: string;
  kind: ProjectRecentKind;
  timestamp: string;
  title: string;
};

const MAX_RECENTS = 12;

export function readProjectRecentViews(projectId: string): ProjectRecentView[] {
  const raw = window.localStorage.getItem(storageKey(projectId));
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isRecentView).slice(0, MAX_RECENTS);
  } catch {
    return [];
  }
}

export function recordProjectRecentView(projectId: string, pathname: string) {
  const view = viewFromPath(projectId, pathname);
  if (!view) return;
  const current = readProjectRecentViews(projectId);
  const next = [
    view,
    ...current.filter((item) => item.href !== view.href),
  ].slice(0, MAX_RECENTS);
  window.localStorage.setItem(storageKey(projectId), JSON.stringify(next));
}

function viewFromPath(projectId: string, pathname: string): ProjectRecentView | null {
  const prefix = `/project/${projectId}`;
  if (pathname === prefix) return null;
  const suffix = pathname.slice(prefix.length);
  const now = new Date().toISOString();
  if (suffix === "/samples") {
    return recent("Samples", "Sample table", "samples", pathname, now);
  }
  if (suffix === "/runs") {
    return recent("Runs", "Run history", "runs", pathname, now);
  }
  if (suffix === "/reports") {
    return recent("Reports", "Saved reports", "report", pathname, now);
  }
  if (suffix === "/insights") {
    return recent("Insights", "Saved insights", "insight", pathname, now);
  }
  if (suffix === "/sample-groups") {
    return recent(
      "Sample groups",
      "Saved sample groups",
      "sample-groups",
      pathname,
      now,
    );
  }
  if (suffix === "/qc-policies") {
    return recent("QC policies", "Quality rules", "policies", pathname, now);
  }
  if (suffix === "/database") {
    return recent("Database", "Project data tables", "database", pathname, now);
  }
  if (suffix === "/settings") {
    return recent("Settings", "Project settings", "settings", pathname, now);
  }
  const sampleMatch = suffix.match(/^\/samples\/([^/]+)$/);
  if (sampleMatch) {
    return recent(sampleMatch[1], "Sample detail", "sample", pathname, now);
  }
  const runMatch = suffix.match(/^\/runs\/([^/]+)$/);
  if (runMatch) {
    return recent(runMatch[1], "Run detail", "run", pathname, now);
  }
  return null;
}

function recent(
  title: string,
  description: string,
  kind: ProjectRecentKind,
  href: string,
  timestamp: string,
): ProjectRecentView {
  return { title, description, kind, href, timestamp };
}

function storageKey(projectId: string) {
  return `goodomics:project-recents:${projectId}`;
}

function isRecentView(value: unknown): value is ProjectRecentView {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const item = value as Record<string, unknown>;
  return (
    typeof item.title === "string" &&
    typeof item.description === "string" &&
    typeof item.href === "string" &&
    typeof item.kind === "string" &&
    typeof item.timestamp === "string"
  );
}
