import type { FormHTMLAttributes, ReactNode } from "react";
import { cn } from "../../lib/utils";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./dialog";

const sizeClasses = {
  sm: "max-w-[460px]",
  md: "max-w-[560px]",
  lg: "max-w-[760px]",
} as const;

type AppDialogProps = {
  children?: ReactNode;
  description?: ReactNode;
  error?: ReactNode;
  footer?: ReactNode;
  formProps?: Omit<FormHTMLAttributes<HTMLFormElement>, "children">;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  size?: keyof typeof sizeClasses;
  title: ReactNode;
};

/** Standard application dialog shell for forms and informational content. */
export function AppDialog({
  children,
  description,
  error,
  footer,
  formProps,
  onOpenChange,
  open,
  size = "sm",
  title,
}: AppDialogProps) {
  const content = (
    <>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        {description ? (
          <DialogDescription>{description}</DialogDescription>
        ) : null}
      </DialogHeader>
      {children}
      {error ? (
        <div
          className="rounded-lg border border-[#f0c8c4] bg-[#fff4f2] p-3 text-sm text-[#b42318]"
          role="alert"
        >
          {error}
        </div>
      ) : null}
      {footer ? <DialogFooter>{footer}</DialogFooter> : null}
    </>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={sizeClasses[size]}>
        {formProps ? (
          <form
            {...formProps}
            className={cn("contents", formProps.className)}
          >
            {content}
          </form>
        ) : (
          content
        )}
      </DialogContent>
    </Dialog>
  );
}
