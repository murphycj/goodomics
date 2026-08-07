import type { ValidationError } from "./generated/types.gen";

export class ApiError extends Error {
  readonly status?: number;
  readonly detail?: string | ValidationError[];

  constructor(
    message: string,
    options: { cause?: unknown; detail?: string | ValidationError[]; status?: number } = {},
  ) {
    super(message, { cause: options.cause });
    this.name = "ApiError";
    this.status = options.status;
    this.detail = options.detail;
  }
}

/** Normalize FastAPI string and validation-detail failures for all transports. */
export function toApiError(error: unknown, response?: Response): ApiError {
  if (error instanceof ApiError) return error;
  const detail = fastApiDetail(error);
  return new ApiError(errorMessage(error, detail, response?.status), {
    cause: error,
    detail,
    status: response?.status,
  });
}

function errorMessage(
  error: unknown,
  detail: string | ValidationError[] | undefined,
  status?: number,
) {
  const detailText = detailMessage(detail);
  if (detailText) return detailText;

  const issues = validationIssues(error);
  if (issues.length) {
    return `Invalid API response: ${issues
      .map(({ message, path }) => `${path.join(".") || "response"}: ${message}`)
      .join("; ")}`;
  }

  if (error instanceof Error && error.message) return error.message;
  return status ? `Request failed: ${status}` : "Request failed";
}

function validationIssues(error: unknown) {
  if (!error || typeof error !== "object" || !("issues" in error)) return [];
  if (!Array.isArray(error.issues)) return [];
  return error.issues.flatMap((issue) => {
    if (!issue || typeof issue !== "object") return [];
    const message = "message" in issue ? issue.message : undefined;
    const path = "path" in issue ? issue.path : undefined;
    if (typeof message !== "string" || !Array.isArray(path)) return [];
    return [{ message, path: path.map(String) }];
  });
}

function fastApiDetail(error: unknown): string | ValidationError[] | undefined {
  if (typeof error === "string") return error;
  if (!error || typeof error !== "object" || !("detail" in error)) return undefined;
  const detail = error.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail as ValidationError[];
  return undefined;
}

function detailMessage(
  detail: string | ValidationError[] | undefined,
) {
  if (typeof detail === "string") return detail;
  if (detail?.length) {
    return detail
      .map((item) => `${item.loc.join(".")}: ${item.msg}`)
      .join("; ");
  }
  return undefined;
}
