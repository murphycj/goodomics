import { create } from "zustand";

type SearchStore = {
  askDraft: string;
  askNonce: number;
  askOpen: boolean;
  askWidth: number;
  closeAsk: () => void;
  closeSearch: () => void;
  draftSearch: string;
  open: boolean;
  openAsk: (draft?: string) => void;
  openSearch: (draft?: string) => void;
  setAskWidth: (width: number) => void;
};

export const useSearchStore = create<SearchStore>((set) => ({
  askDraft: "",
  askNonce: 0,
  askOpen: false,
  askWidth: 430,
  closeAsk: () => set({ askOpen: false }),
  closeSearch: () => set({ open: false, draftSearch: "" }),
  draftSearch: "",
  open: false,
  openAsk: (draft = "") =>
    set((state) => ({
      askDraft: draft,
      askNonce: state.askNonce + 1,
      askOpen: true,
      open: false,
    })),
  openSearch: (draft = "") => set({ draftSearch: draft, open: true }),
  setAskWidth: (width) => set({ askWidth: width }),
}));
