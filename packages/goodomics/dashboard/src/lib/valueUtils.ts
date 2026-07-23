export type UnknownRecord = Record<string, unknown>;

/** Returns whether an unknown JSON-like value is a non-array object. */
export function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Reads an unknown JSON-like value as a record, or returns null. */
export function recordValue(value: unknown): UnknownRecord | null {
  return isRecord(value) ? value : null;
}

/** Reads a string value without coercing other primitive types. */
export function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

/** Reads a non-blank string value, or returns null. */
export function nonEmptyStringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

/** Reads a finite number value without coercing numeric strings. */
export function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
