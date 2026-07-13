import type { ReactNode } from "react";

/** Standard page heading wrapper used by non-canvas dashboard pages. */
export function Page({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      <div className="mb-5 flex min-w-0 items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="m-0 text-[2rem] font-semibold tracking-normal text-[#1d2430]">
            {title}
          </h1>
          <p className="mb-0 mt-1 text-[#657082]">{subtitle}</p>
        </div>
        {actions && <div className="shrink-0 pt-1">{actions}</div>}
      </div>
      {children}
    </>
  );
}
