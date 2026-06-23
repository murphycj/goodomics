import type { ComponentProps } from "react";
import { Toaster as Sonner } from "sonner";

type ToasterProps = ComponentProps<typeof Sonner>;

export function Toaster({ ...props }: ToasterProps) {
  return (
    <Sonner
      closeButton
      position="bottom-right"
      richColors
      toastOptions={{
        classNames: {
          error: "border-[#f1b4b4]",
          success: "border-[#a7e9c5]",
        },
      }}
      {...props}
    />
  );
}
