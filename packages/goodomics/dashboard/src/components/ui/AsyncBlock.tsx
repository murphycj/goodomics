import type { ReactNode } from "react";
import type { QueryState } from "../../lib/types";

export function AsyncBlock<T>({
  children,
  empty,
  query,
}: {
  children: (data: T) => ReactNode;
  empty: string;
  query: QueryState<T>;
}) {
  if (query.isLoading) return <div className="panel muted">Loading...</div>;
  if (query.error) {
    return <div className="panel error">{query.error.message}</div>;
  }
  if (Array.isArray(query.data) && query.data.length === 0) {
    return <div className="panel muted">{empty}</div>;
  }
  if (!query.data) return <div className="panel muted">{empty}</div>;
  return <>{children(query.data)}</>;
}
