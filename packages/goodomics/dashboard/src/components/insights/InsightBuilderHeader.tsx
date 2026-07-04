import { ArrowLeft, BarChart3, ChevronDown, Save } from "lucide-react";
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
      <Input
        className="mt-3"
        placeholder="Enter description (optional)"
        value={description}
        onChange={(event) => onDescriptionChange(event.target.value)}
      />
    </section>
  );
}
