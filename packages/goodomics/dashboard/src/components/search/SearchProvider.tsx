import { type ReactNode, useMemo } from "react";
import { SearchOverlay } from "./SearchOverlay";
import { useSearchStore } from "./searchStore";

export function SearchProvider({
  children,
  defaultProjectId,
  defaultProjectName,
}: {
  children: ReactNode;
  defaultProjectId?: string;
  defaultProjectName?: string;
}) {
  const closeSearch = useSearchStore((state) => state.closeSearch);
  const open = useSearchStore((state) => state.open);

  return (
    <>
      {children}
      <SearchOverlay
        defaultProjectId={defaultProjectId}
        defaultProjectName={defaultProjectName}
        onClose={closeSearch}
        open={open}
      />
    </>
  );
}

export function useSearch() {
  const closeSearch = useSearchStore((state) => state.closeSearch);
  const openSearch = useSearchStore((state) => state.openSearch);

  return useMemo(
    () => ({
      closeSearch,
      openSearch,
    }),
    [closeSearch, openSearch],
  );
}
