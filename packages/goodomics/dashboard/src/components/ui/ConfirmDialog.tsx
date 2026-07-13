import type { ReactNode } from "react";
import { AppDialog } from "./AppDialog";
import { Button } from "./button";

type ConfirmDialogProps = {
  confirmLabel: string;
  description: ReactNode;
  error?: ReactNode;
  isPending?: boolean;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  title: ReactNode;
  tone?: "default" | "destructive";
};

/** Request explicit confirmation before a consequential application action. */
export function ConfirmDialog({
  confirmLabel,
  description,
  error,
  isPending = false,
  onConfirm,
  onOpenChange,
  open,
  title,
  tone = "default",
}: ConfirmDialogProps) {
  return (
    <AppDialog
      description={description}
      error={error}
      footer={
        <>
          <Button
            disabled={isPending}
            variant="secondary"
            onClick={() => onOpenChange(false)}
            type="button"
          >
            Cancel
          </Button>
          <Button
            className={
              tone === "destructive"
                ? "bg-[#b42318] text-white hover:bg-[#912018]"
                : undefined
            }
            disabled={isPending}
            onClick={onConfirm}
            type="button"
          >
            {isPending ? "Working…" : confirmLabel}
          </Button>
        </>
      }
      onOpenChange={(nextOpen) => {
        if (!isPending) onOpenChange(nextOpen);
      }}
      open={open}
      title={title}
    />
  );
}
