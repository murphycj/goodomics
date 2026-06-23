import { toast } from "sonner";

export type ToastParamsByCode = {
  clipboard_copy_failed: { projectRef: string };
  project_ref_copied: { projectRef: string };
};

export type ToastCode = keyof ToastParamsByCode;

type ToastType = "error" | "success";

type ToastDefinition<TParams> = {
  description: (params: TParams) => string;
  duration: number;
  title: string;
  type: ToastType;
};

const toastCatalog = {
  clipboard_copy_failed: {
    description: ({ projectRef }) =>
      `Copy ${projectRef} manually if clipboard access is unavailable.`,
    duration: 5000,
    title: "Could not copy project ref",
    type: "error",
  },
  project_ref_copied: {
    description: ({ projectRef }) => projectRef,
    duration: 2500,
    title: "Project ref copied",
    type: "success",
  },
} satisfies {
  [Code in ToastCode]: ToastDefinition<ToastParamsByCode[Code]>;
};

export function showToast<Code extends ToastCode>(
  code: Code,
  params: ToastParamsByCode[Code],
) {
  const definition = toastCatalog[code];
  toast[definition.type](definition.title, {
    description: definition.description(params),
    duration: definition.duration,
  });
}
