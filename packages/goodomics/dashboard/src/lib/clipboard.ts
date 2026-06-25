export async function writeClipboardText(value: string) {
  try {
    await navigator.clipboard.writeText(value);
    return;
  } catch {
    const textArea = document.createElement("textarea");
    textArea.value = value;
    textArea.setAttribute("readonly", "");
    textArea.style.left = "-9999px";
    textArea.style.position = "fixed";
    textArea.style.top = "0";
    document.body.appendChild(textArea);
    textArea.select();
    try {
      if (!document.execCommand("copy")) {
        throw new Error("Copy command failed.");
      }
    } finally {
      document.body.removeChild(textArea);
    }
  }
}
