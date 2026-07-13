import { ArrowLeft, BarChart3, ChevronDown, Save, X } from "lucide-react";
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
  descriptionOpen,
  isSaving,
  canSave,
  onBack,
  onDescriptionChange,
  onDescriptionOpenChange,
  onSave,
  onSaveContinue,
  onTitleChange,
}: {
  title: string;
  description: string;
  descriptionOpen: boolean;
  isSaving: boolean;
  canSave: boolean;
  onBack: () => void;
  onDescriptionChange: (value: string) => void;
  onDescriptionOpenChange: (value: boolean) => void;
  onSave: () => void;
  onSaveContinue: () => void;
  onTitleChange: (value: string) => void;
}) {
  return (
    <section className="shrink-0 border-b border-[#dce3eb] pb-1">
      <div className="flex items-center gap-1.5">
        <Button size="icon" variant="ghost" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <BarChart3 className="h-5 w-5 text-[#16784a]" />
        <Input
          className="h-8 flex-1 px-2.5 text-base font-semibold"
          value={title}
          onChange={(event) => onTitleChange(event.target.value)}
        />
        {canSave && <div className="flex overflow-hidden rounded-lg">
          <Button
            className="h-8 rounded-r-none"
            disabled={isSaving}
            onClick={onSave}
          >
            <Save className="h-4 w-4" /> Save
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                aria-label="Save options"
                className="h-8 rounded-l-none border-l border-[#16864f] px-2.5"
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
        </div>}
      </div>
      {descriptionOpen ? (
        <div className="mt-1 flex items-start gap-1.5">
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
            onClick={() => onDescriptionOpenChange(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ) : null}
    </section>
  );
}
