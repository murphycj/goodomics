export function SummaryTile({
  label,
  value,
}: {
  label: string;
  value: number | string;
}) {
  return (
    <div className="rounded-lg border border-[#dce3eb] bg-white p-4 shadow-[0_14px_34px_rgb(25_32_43/0.05)]">
      <span className="mb-1.5 block text-xs font-bold uppercase text-[#657082]">
        {label}
      </span>
      <strong className="block text-xl tracking-normal">
        {typeof value === "number" ? value.toLocaleString() : value}
      </strong>
    </div>
  );
}
