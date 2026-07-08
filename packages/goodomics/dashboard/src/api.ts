import { z } from 'zod';

const idSchema = z.union([z.string(), z.number()]);

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
  default_report_id: z.string().nullable(),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
  created_at: z.string(),
  run_count: z.number(),
  sample_count: z.number(),
  subject_count: z.number(),
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
  run_id: idSchema,
  data_contract_id: idSchema,
  run_sample_id: idSchema.nullable(),
  sample_id: idSchema.nullable(),
  field_id: idSchema,
  value_type: z.string(),
  value: z.unknown().nullable(),
  source_file_id: idSchema.nullable(),
  source_observation_id: z.string().nullable().optional(),
  source_observation_label: z.string().nullable().optional(),
  source_observation_metadata_json: z.record(z.string(), z.unknown()).default({}),
});

const analyticsPayloadSchema = z.object({
  run_id: idSchema,
  data_contract_id: idSchema,
  run_sample_id: idSchema.nullable(),
  sample_id: idSchema.nullable(),
  field_id: idSchema,
  payload_name: z.string(),
  payload_kind: z.string(),
  storage_format: z.string(),
  schema_json: z.record(z.string(), z.unknown()),
  data_json: z.unknown(),
  columns: z.array(z.string()),
  rows: z.array(z.record(z.string(), z.unknown())),
  row_count: z.number(),
  source_file_id: idSchema.nullable(),
  source_observation_id: z.string().nullable().optional(),
  source_observation_label: z.string().nullable().optional(),
  source_observation_metadata_json: z.record(z.string(), z.unknown()).default({}),
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

const databaseTableSchema = z.object({
  name: z.string(),
  store: z.enum(['catalog', 'analytics']),
  rows: z.number(),
  columns: z.array(z.string()),
  editable: z.boolean(),
});

const databaseTablePageSchema = z.object({
  name: z.string(),
  store: z.enum(['catalog', 'analytics']),
  columns: z.array(z.string()),
  rows: z.array(z.record(z.string(), z.unknown())),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
  sort_by: z.string().nullable(),
  sort_direction: z.enum(['asc', 'desc']).nullable(),
});

const dataContractFieldSchema = z.object({
  field_id: z.string(),
  field_role: z.string(),
  entity_scope: z.string().nullable(),
  display_name: z.string(),
  value_type: z.string(),
  unit: z.string().nullable(),
  direction: z.string().nullable(),
  description: z.string().nullable(),
  priority: z.string().nullable(),
  primary_table: z.string().nullable(),
  physical_tables: z.record(z.string(), z.unknown()).default({}),
  query_ref: z.record(z.string(), z.unknown()).default({}),
  summary: z.record(z.string(), z.unknown()).default({}),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
});

const dataContractSchema = z.object({
  data_contract_id: z.string(),
  name: z.string(),
  data_type: z.string(),
  assay: z.string().nullable(),
  entity_grain: z.string().nullable(),
  value_semantics: z.string().nullable(),
  summary: z.record(z.string(), z.unknown()).default({}),
  last_profiled_at: z.string().nullable(),
  source_fingerprint: z.string().nullable(),
  query_modes: z.record(z.string(), z.unknown()).default({}),
  description: z.string().nullable(),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
  fields: z.array(dataContractFieldSchema).default([]),
});

const insightSchema = z.object({
  insight_id: z.string(),
  url_slug: z.string(),
  project_id: z.string().nullable(),
  name: z.string(),
  description: z.string().nullable(),
  config: z.record(z.string(), z.unknown()),
  created_at: z.string(),
  updated_at: z.string(),
});

const reportSchema = z.object({
  report_id: z.string(),
  url_slug: z.string(),
  project_id: z.string().nullable(),
  name: z.string(),
  description: z.string().nullable(),
  config: z.record(z.string(), z.unknown()),
  created_at: z.string(),
  updated_at: z.string(),
});

const insightResultSchema = z.object({
  result: z.record(z.string(), z.unknown()),
});

const reportResultSchema = z.object({
  result: z.record(z.string(), z.unknown()),
});

const insightCatalogSchema = z.object({
  version: z.number(),
  modes: z.array(z.record(z.string(), z.unknown())).default([]),
  charts: z.array(z.record(z.string(), z.unknown())).default([]),
  linkers: z.array(z.record(z.string(), z.unknown())).default([]),
  result_policies: z.array(z.record(z.string(), z.unknown())).default([]),
  validation_messages: z.record(z.string(), z.unknown()).default({}),
});

const insightValidationSchema = z.object({
  valid: z.boolean(),
  messages: z.array(z.record(z.string(), z.unknown())).default([]),
  normalized_config: z.record(z.string(), z.unknown()),
  explanation: z.string(),
  catalog_version: z.number(),
});

const sampleSetSchema = z.object({
  sample_set_id: z.string(),
  url_slug: z.string(),
  project_id: z.string().nullable(),
  name: z.string(),
  kind: z.string(),
  description: z.string().nullable(),
  definition_json: z.record(z.string(), z.unknown()).default({}),
  metadata_json: z.record(z.string(), z.unknown()).default({}),
  created_at: z.string(),
  updated_at: z.string(),
  member_count: z.number(),
});

const sampleSetPageSchema = z.object({
  items: z.array(sampleSetSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

const sampleGroupMemberSchema = z.object({
  run_sample_id: z.string(),
  sample_id: z.string(),
  sample_name: z.string().nullable(),
  subject_id: z.string().nullable(),
  run_id: z.string(),
  run_name: z.string().nullable(),
  status: z.string(),
});

const sampleGroupMemberPageSchema = z.object({
  items: z.array(sampleGroupMemberSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
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
export type DatabaseTable = z.infer<typeof databaseTableSchema>;
export type DatabaseTablePage = z.infer<typeof databaseTablePageSchema>;
export type DataContract = z.infer<typeof dataContractSchema>;
export type DataContractField = z.infer<typeof dataContractFieldSchema>;
export type SavedInsight = z.infer<typeof insightSchema>;
export type SavedReport = z.infer<typeof reportSchema>;
export type InsightResult = z.infer<typeof insightResultSchema>['result'];
export type ReportResult = z.infer<typeof reportResultSchema>['result'];
export type InsightCatalog = z.infer<typeof insightCatalogSchema>;
export type InsightValidation = z.infer<typeof insightValidationSchema>;
export type SampleSet = z.infer<typeof sampleSetSchema>;
export type SampleSetPage = z.infer<typeof sampleSetPageSchema>;
export type SampleGroupMember = z.infer<typeof sampleGroupMemberSchema>;
export type SampleGroupMemberPage = z.infer<typeof sampleGroupMemberPageSchema>;
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

async function sendJson<T>(
  path: string,
  method: 'POST' | 'PATCH' | 'DELETE',
  payload: Record<string, unknown> | null,
  schema: z.ZodType<T>,
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: payload ? { 'Content-Type': 'application/json' } : undefined,
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail =
      body && typeof body === 'object' && 'detail' in body
        ? String(body.detail)
        : `Request failed: ${response.status}`;
    throw new Error(detail);
  }
  return schema.parse(await response.json());
}

export function fileContentUrl(file: Pick<StoredFile, 'file_id'>, projectId?: string) {
  if (projectId) {
    return `/api/v1/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(file.file_id)}/content`;
  }
  return `/api/v1/files/${encodeURIComponent(file.file_id)}/content`;
}

export function listRuns({
  limit,
  offset,
  search,
}: {
  limit: number;
  offset: number;
  search?: string;
}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (search?.trim()) params.set('search', search.trim());
  return getJson(`/api/v1/runs?${params.toString()}`, runPageSchema);
}

export function listProjectRuns({
  limit,
  offset,
  projectId,
  search,
}: {
  limit: number;
  offset: number;
  projectId: string;
  search?: string;
}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (search?.trim()) params.set('search', search.trim());
  return getJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/runs?${params.toString()}`,
    runPageSchema,
  );
}

export function listProjectSamples({
  limit,
  offset,
  projectId,
  search,
}: {
  limit: number;
  offset: number;
  projectId: string;
  search?: string;
}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (search?.trim()) params.set("search", search.trim());
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

export async function patchProject(
  projectId: string,
  payload: { default_report_id?: string | null; name?: string; description?: string | null },
) {
  const response = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
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

export function listProjectDatabaseTables(projectId: string) {
  const params = new URLSearchParams({ project_id: projectId });
  return getJson(`/api/v1/database/tables?${params.toString()}`, z.array(databaseTableSchema));
}

export function listProjectDataContracts(projectId: string) {
  const params = new URLSearchParams({ project_id: projectId });
  return getJson(`/api/v1/contracts?${params.toString()}`, z.array(dataContractSchema));
}

export function getInsightCatalog() {
  return getJson('/api/v1/insights/catalog', insightCatalogSchema);
}

export async function validateInsightConfig(config: Record<string, unknown>) {
  const response = await fetch('/api/v1/insights/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config }),
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return insightValidationSchema.parse(await response.json());
}

export function listSampleSets(projectId: string, kind?: string) {
  const params = new URLSearchParams({ project_id: projectId });
  if (kind) params.set('kind', kind);
  return getJson(`/api/v1/sample-sets?${params.toString()}`, z.array(sampleSetSchema));
}

export function listProjectSampleGroups({
  kind,
  limit,
  offset,
  projectId,
  search,
}: {
  kind?: string;
  limit: number;
  offset: number;
  projectId: string;
  search?: string;
}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (kind) params.set('kind', kind);
  if (search?.trim()) params.set('search', search.trim());
  return getJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/sample-groups?${params.toString()}`,
    sampleSetPageSchema,
  );
}

export function createProjectSampleGroup(
  projectId: string,
  payload: {
    description?: string | null;
    kind?: string;
    name: string;
    sample_ids?: string[];
  },
) {
  return sendJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/sample-groups`,
    'POST',
    payload,
    sampleSetSchema,
  );
}

export function getProjectSampleGroup(projectId: string, sampleGroupRef: string) {
  return getJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/sample-groups/${encodeURIComponent(sampleGroupRef)}`,
    sampleSetSchema,
  );
}

export function patchProjectSampleGroup(
  projectId: string,
  sampleSetId: string,
  payload: {
    description?: string | null;
    kind?: string;
    metadata_json?: Record<string, unknown>;
    name?: string;
  },
) {
  return sendJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/sample-groups/${encodeURIComponent(sampleSetId)}`,
    'PATCH',
    payload,
    sampleSetSchema,
  );
}

export async function deleteProjectSampleGroup(
  projectId: string,
  sampleSetId: string,
) {
  const response = await fetch(
    `/api/v1/projects/${encodeURIComponent(projectId)}/sample-groups/${encodeURIComponent(sampleSetId)}`,
    { method: 'DELETE' },
  );
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
}

export function listProjectSampleGroupMembers({
  limit,
  offset,
  projectId,
  sampleSetId,
  search,
}: {
  limit: number;
  offset: number;
  projectId: string;
  sampleSetId: string;
  search?: string;
}) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (search?.trim()) params.set('search', search.trim());
  return getJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/sample-groups/${encodeURIComponent(sampleSetId)}/members?${params.toString()}`,
    sampleGroupMemberPageSchema,
  );
}

export function addProjectSampleGroupMembers(
  projectId: string,
  sampleSetId: string,
  sampleIds: string[],
) {
  return sendJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/sample-groups/${encodeURIComponent(sampleSetId)}/members`,
    'POST',
    { sample_ids: sampleIds },
    sampleSetSchema,
  );
}

export function removeProjectSampleGroupMembers(
  projectId: string,
  sampleSetId: string,
  runSampleIds: string[],
) {
  return sendJson(
    `/api/v1/projects/${encodeURIComponent(projectId)}/sample-groups/${encodeURIComponent(sampleSetId)}/members`,
    'DELETE',
    { run_sample_ids: runSampleIds },
    sampleSetSchema,
  );
}

export function getProjectDataContract(projectId: string, dataContractId: string) {
  const params = new URLSearchParams({ project_id: projectId });
  return getJson(
    `/api/v1/contracts/${encodeURIComponent(dataContractId)}?${params.toString()}`,
    dataContractSchema,
  );
}

export function previewProjectDatabaseTable({
  projectId,
  store,
  table,
  limit,
  offset,
  sortBy,
  sortDirection,
}: {
  projectId: string;
  store: DatabaseTable['store'];
  table: string;
  limit: number;
  offset: number;
  sortBy?: string | null;
  sortDirection?: 'asc' | 'desc' | null;
}) {
  const params = new URLSearchParams({
    project_id: projectId,
    limit: String(limit),
    offset: String(offset),
  });
  if (sortBy && sortDirection) {
    params.set('sort_by', sortBy);
    params.set('sort_direction', sortDirection);
  }
  return getJson(
    `/api/v1/database/${encodeURIComponent(store)}/tables/${encodeURIComponent(table)}/rows?${params.toString()}`,
    databaseTablePageSchema,
  );
}

export function listInsights(projectId: string) {
  const params = new URLSearchParams({ project_id: projectId });
  return getJson(`/api/v1/insights?${params.toString()}`, z.array(insightSchema));
}

export function getInsight(insightId: string) {
  return getJson(`/api/v1/insights/${encodeURIComponent(insightId)}`, insightSchema);
}

export async function createInsight(payload: {
  insight_id?: string;
  project_id: string;
  name: string;
  description?: string | null;
  config: Record<string, unknown>;
}) {
  const response = await fetch('/api/v1/insights', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return insightSchema.parse(await response.json());
}

export async function patchInsight(
  insightId: string,
  payload: { name?: string; description?: string | null; config?: Record<string, unknown> },
) {
  const response = await fetch(`/api/v1/insights/${encodeURIComponent(insightId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return insightSchema.parse(await response.json());
}

export async function deleteInsight(insightId: string) {
  const response = await fetch(`/api/v1/insights/${encodeURIComponent(insightId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
}

export async function executeInsight({
  insightId,
  projectId,
  config,
  refresh,
}: {
  insightId?: string;
  projectId: string;
  config?: Record<string, unknown>;
  refresh?: boolean;
}) {
  const response = await fetch(
    insightId
      ? `/api/v1/insights/${encodeURIComponent(insightId)}/execute`
      : '/api/v1/insights/execute',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        config,
        refresh: Boolean(refresh),
      }),
    },
  );
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return insightResultSchema.parse(await response.json()).result;
}

export function listReports(projectId: string) {
  const params = new URLSearchParams({ project_id: projectId });
  return getJson(`/api/v1/reports?${params.toString()}`, z.array(reportSchema));
}

export function getReport(reportId: string) {
  return getJson(`/api/v1/reports/${encodeURIComponent(reportId)}`, reportSchema);
}

export async function createReport(payload: {
  report_id?: string;
  project_id: string;
  name: string;
  description?: string | null;
  config: Record<string, unknown>;
}) {
  const response = await fetch('/api/v1/reports', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return reportSchema.parse(await response.json());
}

export async function patchReport(
  reportId: string,
  payload: { name?: string; description?: string | null; config?: Record<string, unknown> },
) {
  const response = await fetch(`/api/v1/reports/${encodeURIComponent(reportId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return reportSchema.parse(await response.json());
}

export async function deleteReport(reportId: string) {
  const response = await fetch(`/api/v1/reports/${encodeURIComponent(reportId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
}

export async function executeReport({
  reportId,
  projectId,
  refresh,
}: {
  reportId: string;
  projectId: string;
  refresh?: boolean;
}) {
  const response = await fetch(`/api/v1/reports/${encodeURIComponent(reportId)}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId, refresh: Boolean(refresh) }),
  });
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return reportResultSchema.parse(await response.json()).result;
}

export function listNamedRows(path: string) {
  return getJson(path, z.array(z.record(z.string(), z.unknown())));
}
