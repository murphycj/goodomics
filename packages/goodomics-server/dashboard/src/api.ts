import { z } from 'zod';

const runSchema = z.object({
  run_id: z.string(),
  project: z.string().nullable(),
  assay: z.string().nullable(),
  created_at: z.string(),
  samples: z.array(z.unknown()).default([]),
  metrics: z.array(z.unknown()).default([]),
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
export type ReportTemplate = z.infer<typeof templateSchema>;

async function getJson<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return schema.parse(await response.json());
}

export function listRuns() {
  return getJson('/api/v1/runs', z.array(runSchema));
}

export function listTemplates() {
  return getJson('/api/v1/report-templates', z.array(templateSchema));
}

export function listNamedRows(path: string) {
  return getJson(path, z.array(z.record(z.string(), z.unknown())));
}
