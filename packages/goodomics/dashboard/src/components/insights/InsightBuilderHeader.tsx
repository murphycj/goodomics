import { useEffect, useState } from "react";
import {
  ArrowLeft,
  BarChart3,
  ChevronDown,
  Pencil,
  Plus,
  Save,
  X,
} from "lucide-react";
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Input,
} from "../ui";

export function InsightBuilderHeader({
  title,
  description,
  isSaving,
  onBack,
  onDescriptionChange,
  onSave,
  onSaveContinue,
  onTitleChange,
}: {
  title: string;
  description: string;
  isSaving: boolean;
  onBack: () => void;
  onDescriptionChange: (value: string) => void;
  onSave: () => void;
  onSaveContinue: () => void;
  onTitleChange: (value: string) => void;
}) {
  const hasDescription = Boolean(description.trim());
  const [showDescription, setShowDescription] = useState(
    hasDescription,
  );

  useEffect(() => {
    if (description.trim()) setShowDescription(true);
  }, [description]);

  return (
    <section className="shrink-0 border-b border-[#dce3eb] pb-4">
      <div className="flex items-center gap-3">
        <Button size="icon" variant="ghost" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <BarChart3 className="h-5 w-5 text-[#16784a]" />
        <Input
          className="h-10 flex-1 text-lg font-semibold"
          value={title}
          onChange={(event) => onTitleChange(event.target.value)}
        />
        <Button
          className="bg-[#eef2f6] text-[#526071] hover:bg-[#e3e9f0] hover:text-[#1f2937]"
          type="button"
          variant="ghost"
          onClick={() => setShowDescription(true)}
        >
          {hasDescription ? (
            <>
              <Pencil className="h-4 w-4" /> Description
            </>
          ) : (
            <>
              <Plus className="h-4 w-4" /> Description
            </>
          )}
        </Button>
        <div className="flex overflow-hidden rounded-lg shadow-sm">
          <Button
            className="rounded-r-none"
            disabled={isSaving}
            onClick={onSave}
          >
            <Save className="h-4 w-4" /> Save
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                aria-label="Save options"
                className="rounded-l-none border-l border-[#16864f] px-2.5"
                disabled={isSaving}
              >
                <ChevronDown className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[240px]">
              <DropdownMenuItem onClick={onSaveContinue}>
                <Save className="h-4 w-4" /> Save & continue editing
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      {showDescription ? (
        <div className="mt-3 flex items-start gap-2">
          <textarea
            className="h-10 min-h-10 flex-1 resize-y rounded-md border border-[#d6dee8] bg-white px-3 py-2 text-sm text-[#1f2937] outline-none transition-colors placeholder:text-[#9ca3af] focus:border-[#16784a] focus:ring-2 focus:ring-[#16784a]/15"
            placeholder="Enter description (optional)"
            rows={1}
            value={description}
            onChange={(event) => onDescriptionChange(event.target.value)}
          />
          <Button
            aria-label="Hide description"
            className="mt-1 shrink-0 text-[#657082] hover:text-[#1f2937]"
            size="icon"
            type="button"
            variant="ghost"
            onClick={() => setShowDescription(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ) : null}
    </section>
  );
}
