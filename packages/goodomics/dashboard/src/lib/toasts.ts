import { toast } from "sonner";

export type ToastParamsByCode = {
  clipboard_copy_failed: { projectRef: string };
  database_rows_copied: { count: number; format: string };
  database_rows_copy_failed: { tableName: string };
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
  database_rows_copied: {
    description: ({ count, format }) =>
      `${count.toLocaleString()} selected ${count === 1 ? "row" : "rows"} copied as ${format}.`,
    duration: 2500,
    title: "Selection copied",
    type: "success",
  },
  database_rows_copy_failed: {
    description: ({ tableName }) =>
      `Copy the selected rows from ${tableName} manually if clipboard access is unavailable.`,
    duration: 5000,
    title: "Could not copy selection",
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
  const definition = toastCatalog[code] as ToastDefinition<ToastParamsByCode[Code]>;
  toast[definition.type](definition.title, {
    description: definition.description(params),
    duration: definition.duration,
  });
}
