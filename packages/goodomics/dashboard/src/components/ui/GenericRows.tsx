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
        <pre className="json-block">{JSON.stringify(rows, null, 2)}</pre>
      )}
    </AsyncBlock>
  );
}
