import { z } from 'zod';

const runSchema = z.object({
  run_id: z.string(),
  project_id: z.string().nullable(),
  project: z.string().nullable(),
  name: z.string().nullable(),
  run_kind: z.string().default('pipeline_run'),
  assay: z.string().nullable(),
  status: z.string().default('unknown'),
  created_at: z.string(),
  samples: z.array(z.unknown()).default([]),
  metrics: z.array(z.unknown()).default([]),
});

const runPageSchema = z.object({
  items: z.array(runSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

const projectSchema = z.object({
  project_id: z.string(),
  slug: z.string().nullable(),
  name: z.string(),
  description: z.string().nullable(),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
  created_at: z.string(),
  run_count: z.number(),
  sample_count: z.number(),
  latest_activity_at: z.string().nullable(),
});

const sampleSchema = z.object({
  sample_id: z.string(),
  project_id: z.string().nullable(),
  subject_id: z.string().nullable(),
  external_id: z.string().nullable(),
  sample_name: z.string().nullable(),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
});

const searchResultSchema = z.object({
  kind: z.string(),
  project_id: z.string().nullable(),
  project_name: z.string().nullable(),
  run_id: z.string().nullable().optional(),
  sample_id: z.string().nullable().optional(),
  sample_name: z.string().nullable(),
});

const fileSchema = z.object({
  id: z.number(),
  file_id: z.string().nullable(),
  run_id: z.string(),
  kind: z.string(),
  path: z.string(),
  size_bytes: z.number().nullable(),
  sha256: z.string().nullable(),
  source_path: z.string().nullable(),
  created_at: z.string().nullable(),
});

const analyticsMetricSchema = z.object({
  run_id: z.string(),
  data_profile_key: z.string(),
  run_sample_key: z.string().nullable(),
  sample_key: z.string().nullable(),
  metric_key: z.string(),
  value: z.union([z.number(), z.string()]),
  source_file_id: z.string().nullable(),
});

const analyticsPayloadSchema = z.object({
  run_id: z.string(),
  data_profile_key: z.string(),
  run_sample_key: z.string().nullable(),
  payload_name: z.string(),
  payload_kind: z.string(),
  storage_format: z.string(),
  columns: z.array(z.string()),
  rows: z.array(z.record(z.string(), z.unknown())),
  row_count: z.number(),
  source_file_id: z.string().nullable(),
  source_hash: z.string().nullable(),
});

const tableCountSchema = z.object({
  name: z.string(),
  rows: z.number(),
});

const databaseSummarySchema = z.object({
  sqlite_size_bytes: z.number(),
  duckdb_size_bytes: z.number(),
  file_size_bytes: z.number(),
  total_runs: z.number(),
  total_samples: z.number(),
  total_scalar_metrics: z.number(),
  total_payloads: z.number(),
  control_tables: z.array(tableCountSchema),
  analytics_tables: z.array(tableCountSchema),
});

const templateSchema = z.object({
  template_id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  config: z.record(z.string(), z.unknown()),
  created_at: z.string(),
  updated_at: z.string(),
});

export type GoodomicsRun = z.infer<typeof runSchema>;
export type RunsPage = z.infer<typeof runPageSchema>;
export type GoodomicsProject = z.infer<typeof projectSchema>;
export type GoodomicsSample = z.infer<typeof sampleSchema>;
export type SearchResult = z.infer<typeof searchResultSchema>;
export type StoredFile = z.infer<typeof fileSchema>;
export type AnalyticsMetric = z.infer<typeof analyticsMetricSchema>;
export type AnalyticsPayload = z.infer<typeof analyticsPayloadSchema>;
export type DatabaseSummary = z.infer<typeof databaseSummarySchema>;
export type ReportTemplate = z.infer<typeof templateSchema>;

async function getJson<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return schema.parse(await response.json());
}

export function fileContentUrl(file: Pick<StoredFile, 'file_id' | 'id'>, projectId?: string) {
  if (projectId) {
    return `/api/v1/projects/${encodeURIComponent(projectId)}/files/${file.id}/content`;
  }
  return `/api/v1/files/${file.id}/content`;
}

export function listRuns({ limit, offset }: { limit: number; offset: number }) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return getJson(`/api/v1/runs?${params.toString()}`, runPageSchema);
}

export function listProjectRuns({
  limit,
  offset,
  projectId,
}: {
  limit: number;
  offset: number;
  projectId: string;
}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return getJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/runs?${params.toString()}`,
    runPageSchema,
  );
}

export function listProjects() {
  return getJson('/api/v1/projects', z.array(projectSchema));
}

export function getProject(projectId: string) {
  return getJson(`/api/v1/projects/${encodeURIComponent(projectId)}`, projectSchema);
}

export function getProjectSample(projectId: string, sampleId: string) {
  return getJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/samples/${encodeURIComponent(sampleId)}`,
    sampleSchema,
  );
}

export async function createProject(payload: {
  name: string;
  slug?: string;
  description?: string;
}) {
  const response = await fetch('/api/v1/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return projectSchema.parse(await response.json());
}

export function searchSamples({ projectId, query }: { projectId?: string; query: string }) {
  const params = new URLSearchParams({ q: query });
  if (projectId) params.set('project_id', projectId);
  return getJson(`/api/v1/search?${params.toString()}`, z.array(searchResultSchema));
}

export function getProjectRun(projectId: string, runId: string) {
  return getJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}`,
    runSchema,
  );
}

export function listProjectRunFiles(projectId: string, runId: string) {
  return getJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/files`,
    z.array(fileSchema),
  );
}

export function listProjectRunMetrics(projectId: string, runId: string) {
  return getJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/analytics/metrics`,
    z.array(analyticsMetricSchema),
  );
}

export function listProjectRunPayloads(projectId: string, runId: string) {
  return getJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/runs/${encodeURIComponent(runId)}/analytics/payloads`,
    z.array(analyticsPayloadSchema),
  );
}

export function getDatabaseSummary() {
  return getJson('/api/v1/database/summary', databaseSummarySchema);
}

export function getProjectDatabaseSummary(projectId: string) {
  const params = new URLSearchParams({ project_id: projectId });
  return getJson(`/api/v1/database/summary?${params.toString()}`, databaseSummarySchema);
}

export function listTemplates() {
  return getJson('/api/v1/report-templates', z.array(templateSchema));
}

export function listNamedRows(path: string) {
  return getJson(path, z.array(z.record(z.string(), z.unknown())));
}
