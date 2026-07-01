import { Search } from "lucide-react";

/** Inline search input with a leading search icon. */
export function SearchBox({
  onChange,
  placeholder,
  value,
}: {
  onChange: (value: string) => void;
  placeholder: string;
  value: string;
}) {
  return (
    <label className="my-4 inline-flex max-w-[420px] cursor-text items-center gap-2 rounded-lg border border-[#dce3eb] bg-white px-3 py-2">
      <Search size={16} className="shrink-0 text-[#657082]" />
      <input
        className="w-full border-0 bg-transparent text-sm text-[#1d2430] outline-none placeholder:text-[#9ca3af]"
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        value={value}
      />
    </label>
  );
}
