import { Copy } from "lucide-react";
import type { KeyboardEvent, MouseEvent } from "react";
import { writeClipboardText } from "../../lib/clipboard";
import { showToast } from "../../lib/toasts";

/** Icon button that copies a value while preserving parent row click behavior. */
export function CopyButton({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  const copyValue = async (
    event: KeyboardEvent<HTMLButtonElement> | MouseEvent<HTMLButtonElement>,
  ) => {
    event.preventDefault();
    event.stopPropagation();
    try {
      await writeClipboardText(value);
      showToast("project_ref_copied", { projectRef: value });
    } catch {
      showToast("clipboard_copy_failed", { projectRef: value });
    }
  };

  return (
    <button
      aria-label={label}
      className="inline-flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-md border border-[#e8edf3] bg-white text-[#8b95a3] transition-colors hover:border-[#8edeb4] hover:bg-[#eef8f2] hover:text-[#16784a] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#21a66a]"
      onClick={(event) => void copyValue(event)}
      onKeyDown={(event) => event.stopPropagation()}
      title="Copy"
      type="button"
    >
      <Copy size={15} />
    </button>
  );
}
