import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-65 cursor-pointer",
  {
    variants: {
      variant: {
        default: "bg-[#16784a] text-white hover:bg-[#1a8f58]",
        secondary: "bg-[#e7ebf0] text-[#1d2430] hover:bg-[#dde3ea]",
        ghost: "hover:bg-[#f1f5f9] text-[#1d2430]",
        outline:
          "border border-[#cfd8e3] bg-white text-[#1d2430] hover:bg-[#eef8f2] hover:border-[#8edeb4]",
      },
      size: {
        default: "min-h-[2.25rem] px-[0.85rem] py-[0.55rem]",
        sm: "min-h-[1.9rem] px-[0.6rem] py-[0.35rem] text-xs",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
