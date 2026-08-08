import { useEffect, useState } from "react";
import { AppDialog, Button, Input } from "../ui";

/** Rename dialog shared by saved insight and report list actions. */
export function SavedItemRenameDialog({
  error,
  isPending,
  itemName,
  noun,
  onOpenChange,
  onRename,
  open,
}: {
  error?: string;
  isPending: boolean;
  itemName: string;
  noun: "insight" | "report";
  onOpenChange: (open: boolean) => void;
  onRename: (name: string) => void;
  open: boolean;
}) {
  const [name, setName] = useState(itemName);

  useEffect(() => {
    if (open) setName(itemName);
  }, [itemName, open]);

  return (
    <AppDialog
      description={`Enter a new name for “${itemName}”.`}
      error={error}
      footer={
        <>
          <Button
            disabled={isPending}
            type="button"
            variant="secondary"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button
            disabled={isPending || !name.trim()}
            type="button"
            onClick={() => onRename(name.trim())}
          >
            {isPending ? "Renaming…" : "Rename"}
          </Button>
        </>
      }
      onOpenChange={(nextOpen) => {
        if (!isPending) onOpenChange(nextOpen);
      }}
      open={open}
      title={`Rename ${noun}`}
    >
      <Input
        aria-label={`${noun} name`}
        autoFocus
        value={name}
        onChange={(event) => setName(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && name.trim() && !isPending) {
            event.preventDefault();
            onRename(name.trim());
          }
        }}
      />
    </AppDialog>
  );
}
