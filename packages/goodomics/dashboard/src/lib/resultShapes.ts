import type { AnalyticsPayload, DataContractField } from "../api";

type JsonRecord = Record<string, unknown>;

export function fieldTypeLabel(field: DataContractField) {
  if (field.field_role !== "payload") {
    return field.value_type;
  }
  return resultShapeLabel(field.metadata_json.payload_kind);
}

export function fieldShapeSummary(field: DataContractField) {
  if (field.field_role !== "payload") return null;
  const schema = recordValue(field.metadata_json.schema_json);
  if (!schema) return null;
  const x = recordValue(schema.x);
  const y = recordValue(schema.y);
  const xLabel = stringValue(x?.label) ?? stringValue(x?.field);
  const yLabel = stringValue(y?.label) ?? stringValue(y?.field);
  if (xLabel && yLabel) {
    return `${xLabel} vs ${yLabel}`;
  }
  const columns = schema.columns;
  if (Array.isArray(columns) && columns.length > 0) {
    return `${columns.length} columns`;
  }
  return null;
}

export function payloadKindLabel(payload: AnalyticsPayload) {
  return resultShapeLabel(payload.payload_kind);
}

export function payloadShapeSummary(payload: AnalyticsPayload) {
  if (payload.payload_kind === "xy_series") {
    return `${payload.row_count.toLocaleString()} points`;
  }
  if (payload.payload_kind === "matrix") {
    const rows = payload.row_count.toLocaleString();
    const columns = payload.columns.length.toLocaleString();
    return `${rows} x ${columns}`;
  }
  if (payload.payload_kind === "table") {
    return `${payload.row_count.toLocaleString()} rows`;
  }
  if (payload.row_count > 0) {
    return `${payload.row_count.toLocaleString()} rows`;
  }
  return null;
}

function resultShapeLabel(value: unknown) {
  const kind = stringValue(value);
  if (kind === "xy_series") return "Point series";
  if (kind === "matrix") return "Matrix";
  if (kind === "table") return "Table";
  if (kind === "numeric_array") return "Numeric array";
  if (kind === "json") return "JSON object";
  if (kind?.includes("table")) return "Table";
  if (kind?.includes("matrix")) return "Matrix";
  return "Result payload";
}

function recordValue(value: unknown): JsonRecord | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as JsonRecord)
    : null;
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value : null;
}
