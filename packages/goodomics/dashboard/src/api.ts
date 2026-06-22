import { z } from 'zod';

const runSchema = z.object({
  run_id: z.string(),
  project: z.string().nullable(),
  assay: z.string().nullable(),
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
  sample_id: z.string().nullable(),
  metric_key: z.string(),
  tool: z.string().nullable(),
  module: z.string().nullable(),
  stage: z.string().nullable(),
  value_num: z.number().nullable(),
  value_text: z.string().nullable(),
  unit: z.string().nullable(),
  source_file: z.string(),
});

const analyticsPayloadSchema = z.object({
  run_id: z.string(),
  sample_id: z.string().nullable(),
  tool: z.string().nullable(),
  module: z.string().nullable(),
  payload_name: z.string(),
  payload_kind: z.string(),
  columns: z.array(z.string()),
  rows: z.array(z.record(z.string(), z.unknown())),
  row_count: z.number(),
  source_file: z.string(),
  source_hash: z.string(),
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

export function fileContentUrl(file: Pick<StoredFile, 'file_id' | 'id'>) {
  return `/api/v1/files/${file.id}/content`;
}

export function listRuns({ limit, offset }: { limit: number; offset: number }) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return getJson(`/api/v1/runs?${params.toString()}`, runPageSchema);
}

export function getRun(runId: string) {
  return getJson(`/api/v1/runs/${encodeURIComponent(runId)}`, runSchema);
}

export function listRunFiles(runId: string) {
  return getJson(`/api/v1/runs/${encodeURIComponent(runId)}/files`, z.array(fileSchema));
}

export function listRunMetrics(runId: string) {
  return getJson(
    `/api/v1/runs/${encodeURIComponent(runId)}/analytics/metrics`,
    z.array(analyticsMetricSchema),
  );
}

export function listRunPayloads(runId: string) {
  return getJson(
    `/api/v1/runs/${encodeURIComponent(runId)}/analytics/payloads`,
    z.array(analyticsPayloadSchema),
  );
}

export function getDatabaseSummary() {
  return getJson('/api/v1/database/summary', databaseSummarySchema);
}

export function listTemplates() {
  return getJson('/api/v1/report-templates', z.array(templateSchema));
}

export function listNamedRows(path: string) {
  return getJson(path, z.array(z.record(z.string(), z.unknown())));
}
