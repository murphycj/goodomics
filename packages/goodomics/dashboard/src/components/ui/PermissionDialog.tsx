import type { ReactNode } from "react";
import { AppDialog } from "./AppDialog";
import { Button } from "./button";

type PermissionDialogProps = {
  actionIcon?: ReactNode;
  actionLabel: string;
  description: ReactNode;
  onAction: () => void;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  title: ReactNode;
};

/** Explain a permission boundary and offer the action that can resolve it. */
export function PermissionDialog({
  actionIcon,
  actionLabel,
  description,
  onAction,
  onOpenChange,
  open,
  title,
}: PermissionDialogProps) {
  return (
    <AppDialog
      description={description}
      footer={
        <>
          <Button
            variant="secondary"
            onClick={() => onOpenChange(false)}
            type="button"
          >
            Cancel
          </Button>
          <Button onClick={onAction} type="button">
            {actionIcon}
            {actionLabel}
          </Button>
        </>
      }
      onOpenChange={onOpenChange}
      open={open}
      title={title}
    />
  );
}
