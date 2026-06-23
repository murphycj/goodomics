import { create } from "zustand";

type SearchStore = {
  closeSearch: () => void;
  open: boolean;
  openSearch: () => void;
};

export const useSearchStore = create<SearchStore>((set) => ({
  closeSearch: () => set({ open: false }),
  open: false,
  openSearch: () => set({ open: true }),
}));
