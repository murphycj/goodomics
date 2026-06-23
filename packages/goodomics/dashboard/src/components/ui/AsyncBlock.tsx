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
  if (query.isLoading) {
    return (
      <div className="mt-4 rounded-lg border border-[#dce3eb] bg-white p-4 text-[#657082]">
        Loading...
      </div>
    );
  }
  if (query.error) {
    return (
      <div className="mt-4 rounded-lg border border-[#dce3eb] bg-white p-4 text-[#b42318]">
        {query.error.message}
      </div>
    );
  }
  if (Array.isArray(query.data) && query.data.length === 0) {
    return (
      <div className="mt-4 rounded-lg border border-[#dce3eb] bg-white p-4 text-[#657082]">
        {empty}
      </div>
    );
  }
  if (!query.data) {
    return (
      <div className="mt-4 rounded-lg border border-[#dce3eb] bg-white p-4 text-[#657082]">
        {empty}
      </div>
    );
  }
  return <>{children(query.data)}</>;
}
