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
  file_count: z.number(),
  file_size_bytes: z.number(),
  latest_activity_at: z.string().nullable(),
});

const sampleSchema = z.object({
  sample_id: z.string(),
  project_id: z.string().nullable(),
  subject_id: z.string().nullable(),
  sample_name: z.string().nullable(),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
});

const sampleListItemSchema = sampleSchema.extend({
  run_count: z.number(),
  latest_run_id: z.string().nullable(),
  latest_run_name: z.string().nullable(),
  latest_run_created_at: z.string().nullable(),
});

const samplePageSchema = z.object({
  items: z.array(sampleListItemSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

const sampleRunSchema = z.object({
  run_id: z.string(),
  project_id: z.string().nullable(),
  name: z.string().nullable(),
  run_kind: z.string(),
  assay: z.string().nullable(),
  pipeline_name: z.string().nullable(),
  pipeline_version: z.string().nullable(),
  status: z.string(),
  created_at: z.string(),
  run_sample_id: z.string(),
  run_sample_status: z.string(),
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
  file_id: z.string(),
  project_id: z.string().nullable(),
  run_id: z.string().nullable(),
  kind: z.string(),
  path: z.string().nullable(),
  uri: z.string().nullable(),
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

const aiMessageSchema = z.object({
  role: z.string(),
  content: z.string(),
});

const aiToolEvidenceSchema = z.object({
  name: z.string(),
  arguments: z.record(z.string(), z.unknown()).default({}),
  result: z.record(z.string(), z.unknown()).default({}),
});

const aiChatResponseSchema = z.object({
  conversation_id: z.string().nullable(),
  message: aiMessageSchema,
  tool_calls: z.array(aiToolEvidenceSchema).default([]),
});

export type GoodomicsRun = z.infer<typeof runSchema>;
export type RunsPage = z.infer<typeof runPageSchema>;
export type GoodomicsProject = z.infer<typeof projectSchema>;
export type GoodomicsSample = z.infer<typeof sampleSchema>;
export type SampleListItem = z.infer<typeof sampleListItemSchema>;
export type SamplesPage = z.infer<typeof samplePageSchema>;
export type SampleRun = z.infer<typeof sampleRunSchema>;
export type SearchResult = z.infer<typeof searchResultSchema>;
export type StoredFile = z.infer<typeof fileSchema>;
export type AnalyticsMetric = z.infer<typeof analyticsMetricSchema>;
export type AnalyticsPayload = z.infer<typeof analyticsPayloadSchema>;
export type DatabaseSummary = z.infer<typeof databaseSummarySchema>;
export type ReportTemplate = z.infer<typeof templateSchema>;
export type AiMessage = z.infer<typeof aiMessageSchema>;
export type AiToolEvidence = z.infer<typeof aiToolEvidenceSchema>;
export type AiChatResponse = z.infer<typeof aiChatResponseSchema>;

async function getJson<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return schema.parse(await response.json());
}

export function fileContentUrl(file: Pick<StoredFile, 'file_id'>, projectId?: string) {
  if (projectId) {
    return `/api/v1/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(file.file_id)}/content`;
  }
  return `/api/v1/files/${encodeURIComponent(file.file_id)}/content`;
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

export function listProjectSamples({
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
    `/api/v1/projects/${encodeURIComponent(projectId)}/samples?${params.toString()}`,
    samplePageSchema,
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

export function listProjectSampleRuns(projectId: string, sampleId: string) {
  return getJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/samples/${encodeURIComponent(sampleId)}/runs`,
    z.array(sampleRunSchema),
  );
}

export function listProjectSampleRunMetrics(
  projectId: string,
  sampleId: string,
  runId: string,
) {
  return getJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/samples/${encodeURIComponent(sampleId)}/runs/${encodeURIComponent(runId)}/analytics/metrics`,
    z.array(analyticsMetricSchema),
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

export async function askAi({
  conversationId,
  messages,
  projectId,
}: {
  conversationId?: string | null;
  messages: AiMessage[];
  projectId?: string;
}) {
  const response = await fetch('/api/v1/ai/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: conversationId ?? null,
      messages,
      project_id: projectId ?? null,
    }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? String(body.detail)
        : `Request failed: ${response.status}`;
    throw new Error(detail);
  }
  return aiChatResponseSchema.parse(await response.json());
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
