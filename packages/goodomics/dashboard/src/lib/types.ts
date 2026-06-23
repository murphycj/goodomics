export type QueryState<T> = {
  isLoading: boolean;
  error: Error | null;
  data?: T;
};

export type SidebarMode = "expanded" | "collapsed" | "hover";
