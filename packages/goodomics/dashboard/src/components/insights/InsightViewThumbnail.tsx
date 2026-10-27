import { cn } from "../../lib/utils";
import { insightViewIconPath, insightViewLabel } from "../../lib/insightViewCatalog";

/** Reusable generated preview icon for one saved insight view kind. */
export function InsightViewThumbnail({
  className,
  decorative = false,
  kind,
}: {
  className?: string;
  decorative?: boolean;
  kind: string;
}) {
  const label = insightViewLabel(kind);
  return (
    <img
      alt={decorative ? "" : `${label} view`}
      aria-hidden={decorative || undefined}
      className={cn("h-9 w-12 shrink-0 object-contain", className)}
      decoding="async"
      height={72}
      loading={decorative ? "eager" : "lazy"}
      src={insightViewIconPath(kind)}
      title={decorative ? undefined : `${label} view`}
      width={96}
    />
  );
}
