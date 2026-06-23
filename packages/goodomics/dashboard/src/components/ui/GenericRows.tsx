import type { QueryState } from "../../lib/types";
import { AsyncBlock } from "./AsyncBlock";

export function GenericRows<T extends unknown[]>({
  query,
  empty,
}: {
  query: QueryState<T>;
  empty: string;
}) {
  return (
    <AsyncBlock query={query} empty={empty}>
      {(rows) => (
        <pre className="mt-4 overflow-auto rounded-lg border border-[#dce3eb] bg-white p-4 text-sm shadow-[0_14px_34px_rgb(25_32_43/0.05)]">
          {JSON.stringify(rows, null, 2)}
        </pre>
      )}
    </AsyncBlock>
  );
}
