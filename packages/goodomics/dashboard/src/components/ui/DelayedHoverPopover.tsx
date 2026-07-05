import * as React from "react";
import { cn } from "../../lib/utils";

type DelayedHoverPopoverProps = {
  children: React.ReactNode;
  content: React.ReactNode;
  className?: string;
  contentClassName?: string;
  delayMs?: number;
};

/** Delayed hover/focus popover that never pins open after trigger clicks. */
export function DelayedHoverPopover({
  children,
  className,
  content,
  contentClassName,
  delayMs = 500,
}: DelayedHoverPopoverProps) {
  const [open, setOpen] = React.useState(false);
  const timerRef = React.useRef<number | null>(null);

  const clearTimer = React.useCallback(() => {
    if (timerRef.current === null) return;
    window.clearTimeout(timerRef.current);
    timerRef.current = null;
  }, []);

  const scheduleOpen = React.useCallback(() => {
    clearTimer();
    timerRef.current = window.setTimeout(() => {
      setOpen(true);
      timerRef.current = null;
    }, delayMs);
  }, [clearTimer, delayMs]);

  const close = React.useCallback(() => {
    clearTimer();
    setOpen(false);
  }, [clearTimer]);

  React.useEffect(() => clearTimer, [clearTimer]);

  return (
    <div
      className={cn("relative", className)}
      onBlur={close}
      onClick={close}
      onFocus={scheduleOpen}
      onPointerEnter={scheduleOpen}
      onPointerLeave={close}
    >
      {children}
      <div
        aria-hidden={!open}
        className={cn(
          "pointer-events-none absolute left-0 top-full z-30 mt-2 w-[260px] rounded-md border border-[#d6dee8] bg-white p-3 text-xs leading-5 text-[#526071] opacity-0 shadow-[0_14px_36px_rgb(0_0_0/0.14)] transition-opacity duration-150",
          open && "opacity-100",
          contentClassName,
        )}
      >
        {content}
      </div>
    </div>
  );
}
