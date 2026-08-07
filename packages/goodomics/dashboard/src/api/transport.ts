/**
 * Manual transport exceptions for responses the generated JSON SDK does not
 * model well, such as blobs, arbitrary paths, and intentionally dynamic rows.
 * TanStack queries and mutations normally call the generated SDK through
 * `api/index.ts`; add ordinary JSON endpoints to FastAPI and regenerate instead
 * of routing them through this module.
 */

import { accessToken, invalidateAuthentication } from "./auth";
import { toApiError } from "./errors";
import type { FileRead } from "./generated/types.gen";

/** Perform a manual transport request with the generated client's auth lifecycle. */
export async function apiFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
) {
  const headers = new Headers(init.headers);
  const token = accessToken();

  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(input, { ...init, headers });

  if (response.status === 401 && token) invalidateAuthentication();

  return response;
}

/** Throw the central API error representation for an unsuccessful response. */
export async function requireOk(response: Response) {
  if (response.ok) return response;

  const text = await response.text();

  let error: unknown = text;

  try {
    error = JSON.parse(text);
  } catch {
    // Plain-text and empty bodies are valid error responses.
  }

  throw toApiError(error, response);
}

/** Build the arbitrary download URL for a stored file resource. */
export function fileContentUrl(
  file: Pick<FileRead, "file_id">,
  projectId?: string,
) {
  if (projectId) {
    return `/api/v1/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(file.file_id)}/content`;
  }
  return `/api/v1/files/${encodeURIComponent(file.file_id)}/content`;
}

/** Open authenticated file content through a short-lived object URL. */
export async function openFileContent(
  file: Pick<FileRead, "file_id">,
  projectId?: string,
) {
  const response = await requireOk(
    await apiFetch(fileContentUrl(file, projectId)),
  );

  const objectUrl = URL.createObjectURL(await response.blob());

  window.open(objectUrl, "_blank", "noopener,noreferrer");
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}

/** Read intentionally dynamic rows from an arbitrary API path. */
export async function listNamedRows(path: string) {
  const response = await requireOk(await apiFetch(path));
  return (await response.json()) as Record<string, unknown>[];
}
