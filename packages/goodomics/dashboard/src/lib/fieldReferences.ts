/** the purpose of this module is to provide utilities for creating and parsing field references. Some examples:
 `contractFieldReference("contract-123", "field-456")` returns `"contract-123/field-456"`
 `metadataFieldReference("subject", "age")` returns `"metadata/subject/age"`
*/

const METADATA_ENTITIES = new Set(["subject", "sample", "run", "file"]);

export type ParsedFieldReference =
  | { kind: "contract"; contractId: string; fieldId: string }
  | { kind: "metadata"; entity: string; fieldId: string };

function validateSegment(value: string) {
  if (!value || value !== value.trim() || value.includes("/")) {
    throw new Error(
      "Field-reference IDs must be non-empty and cannot contain '/'.",
    );
  }
  return value;
}

export function contractFieldReference(contractId: string, fieldId: string) {
  return `${validateSegment(contractId)}/${validateSegment(fieldId)}`;
}

export function metadataFieldReference(entity: string, fieldId: string) {
  if (!METADATA_ENTITIES.has(entity))
    throw new Error(`Unknown metadata entity: ${entity}.`);
  return `metadata/${entity}/${validateSegment(fieldId)}`;
}

export function parseFieldReference(value: string): ParsedFieldReference {
  if (!value || value !== value.trim())
    throw new Error("Invalid field reference.");
  const parts = value.split("/");
  if (parts.length === 2) {
    return {
      kind: "contract",
      contractId: validateSegment(parts[0]),
      fieldId: validateSegment(parts[1]),
    };
  }
  if (
    parts.length === 3 &&
    parts[0] === "metadata" &&
    METADATA_ENTITIES.has(parts[1])
  ) {
    return {
      kind: "metadata",
      entity: parts[1],
      fieldId: validateSegment(parts[2]),
    };
  }
  throw new Error(
    "Field reference must be '<contract>/<field>' or 'metadata/<entity>/<field>'.",
  );
}

export function isMetadataFieldReference(value: string) {
  try {
    return parseFieldReference(value).kind === "metadata";
  } catch {
    return false;
  }
}

export function valueReference(value: { field: string; as?: string }) {
  return value.as || value.field;
}
