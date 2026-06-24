import { type ReactNode, useMemo } from "react";
import { AskAiSidePanel } from "../ai/AskAiSidePanel";
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
  const askDraft = useSearchStore((state) => state.askDraft);
  const askNonce = useSearchStore((state) => state.askNonce);
  const askOpen = useSearchStore((state) => state.askOpen);
  const askWidth = useSearchStore((state) => state.askWidth);
  const closeAsk = useSearchStore((state) => state.closeAsk);
  const closeSearch = useSearchStore((state) => state.closeSearch);
  const draftSearch = useSearchStore((state) => state.draftSearch);
  const open = useSearchStore((state) => state.open);
  const setAskWidth = useSearchStore((state) => state.setAskWidth);

  return (
    <>
      {children}
      <SearchOverlay
        defaultProjectId={defaultProjectId}
        defaultProjectName={defaultProjectName}
        draft={draftSearch}
        onClose={closeSearch}
        open={open}
      />
      <AskAiSidePanel
        defaultProjectId={defaultProjectId}
        defaultProjectName={defaultProjectName}
        draft={askDraft}
        draftNonce={askNonce}
        onClose={closeAsk}
        open={askOpen}
        setWidth={setAskWidth}
        width={askWidth}
      />
    </>
  );
}

export function useSearch() {
  const closeAsk = useSearchStore((state) => state.closeAsk);
  const closeSearch = useSearchStore((state) => state.closeSearch);
  const openAsk = useSearchStore((state) => state.openAsk);
  const openSearch = useSearchStore((state) => state.openSearch);

  return useMemo(
    () => ({
      closeAsk,
      closeSearch,
      openAsk,
      openSearch,
    }),
    [closeAsk, closeSearch, openAsk, openSearch],
  );
}
