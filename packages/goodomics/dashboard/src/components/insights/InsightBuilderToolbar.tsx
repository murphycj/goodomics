/**
 * InsightBuilderToolbar component for configuring insight analysis and view settings.
 */

import {
  FileText,
  MoreHorizontal,
  Sparkles,
  Trash2,
  Users,
} from "lucide-react";
import { useState } from "react";
import type { InsightDraft, InsightView } from "../../lib/insightSchemas";
import { titleCase } from "../../lib/insightBuilder";
import {
  getInsightViewDefinition,
  INSIGHT_VIEW_OPTIONS,
  insightViewLabel,
  isInsightViewKind,
} from "../../lib/insightViewCatalog";
import {
  Button,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui";
import { InsightSettingsButton } from "./InsightSettingsDrawer";

type BuilderTemplate = {
  id: string;
  label: string;
  grain?: InsightDraft["analysis"]["grain"];
  viewKind?: InsightView["kind"];
};

export function InsightBuilderToolbar({
  draft,
  result,
  templates,
  onChange,
  onClearValues,
  onDescription,
  onGrainChange,
  onTemplate,
  onViewKindChange,
}: {
  draft: InsightDraft;
  result?: Record<string, unknown> | null;
  templates: Record<string, unknown>[];
  onChange: (draft: InsightDraft) => void;
  onClearValues: () => void;
  onDescription: () => void;
  onGrainChange: (grain: InsightDraft["analysis"]["grain"]) => void;
  onTemplate: (template: BuilderTemplate) => void;
  onViewKindChange: (kind: InsightView["kind"]) => void;
}) {
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const availableTemplates = templates
    .map(parseTemplate)
    .filter((template): template is BuilderTemplate => Boolean(template));
  const viewDefinition = getInsightViewDefinition(draft.view.kind);
  return (
    <>
      <section className="flex shrink-0 flex-wrap items-end justify-between gap-3 border-b border-[#dce3eb] pb-2">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label className="text-[11px] font-bold uppercase tracking-wide text-[#657082]">
              Analyze by
            </Label>
            <Select
              value={draft.analysis.grain}
              onValueChange={(grain: InsightDraft["analysis"]["grain"]) =>
                onGrainChange(grain)
              }
            >
              <SelectTrigger
                aria-label="Analyze by"
                className="h-9 min-w-[170px] bg-white"
              >
                <Users className="h-4 w-4 text-[#657082]" /> <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(
                  [
                    "sample",
                    "subject",
                    "run",
                    "feature",
                    "variant",
                    "file",
                  ] as const
                ).map((grain) => (
                  <SelectItem key={grain} value={grain}>
                    {titleCase(`${grain}s`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex items-end gap-1">
          <div className="mr-1 space-y-1">
            <Label className="text-[11px] font-bold uppercase tracking-wide text-[#657082]">
              View as
            </Label>
            <Select
              value={draft.view.kind}
              onValueChange={(kind: InsightView["kind"]) =>
                onViewKindChange(kind)
              }
            >
              <SelectTrigger
                aria-label="View as"
                className="h-9 min-w-[170px] bg-white"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {INSIGHT_VIEW_OPTIONS.map(({ kind, label, icon: ViewIcon }) => {
                  return (
                    <SelectItem key={kind} value={kind}>
                      <span className="flex items-center gap-2">
                        <ViewIcon className="h-4 w-4 text-[#657082]" />
                        {label}
                      </span>
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>
          <InsightSettingsButton
            draft={draft}
            result={result}
            onChange={onChange}
          />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                aria-label="Insight actions"
                size="icon"
                variant="outline"
              >
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-[230px]">
              <DropdownMenuItem onClick={onDescription}>
                <FileText className="h-4 w-4" /> Add or edit description
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setTemplatesOpen(true)}>
                <Sparkles className="h-4 w-4" /> Choose template
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-[#b42318]"
                disabled={!draft.analysis.values.length}
                onClick={() => setClearOpen(true)}
              >
                <Trash2 className="h-4 w-4" /> Clear{" "}
                {viewDefinition.editor.valueNounPlural}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </section>
      <TemplateDialog
        open={templatesOpen}
        templates={availableTemplates}
        onOpenChange={setTemplatesOpen}
        onSelect={(template) => {
          onTemplate(template);
          setTemplatesOpen(false);
        }}
      />
      <ConfirmDialog
        confirmLabel={`Clear ${viewDefinition.editor.valueNounPlural}`}
        description="This removes every selected field and its configuration from the insight."
        open={clearOpen}
        title={`Clear all ${viewDefinition.editor.valueNounPlural}?`}
        tone="destructive"
        onOpenChange={setClearOpen}
        onConfirm={() => {
          onClearValues();
          setClearOpen(false);
        }}
      />
    </>
  );
}

// shows a dialog to choose a template for the insight
function TemplateDialog({
  open,
  templates,
  onOpenChange,
  onSelect,
}: {
  open: boolean;
  templates: BuilderTemplate[];
  onOpenChange: (open: boolean) => void;
  onSelect: (template: BuilderTemplate) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[560px]">
        <DialogHeader>
          <DialogTitle>Choose a starting point</DialogTitle>
          <DialogDescription>
            Templates are pre-configured insights to help you get started
            quickly.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          {templates.map((template) => (
            <button
              className="rounded-lg border border-[#dce3eb] p-4 text-left transition-colors hover:border-[#8edeb4] hover:bg-[#f3faf6]"
              key={template.id}
              type="button"
              onClick={() => onSelect(template)}
            >
              <span className="block text-sm font-semibold text-[#1f2937]">
                {template.label}
              </span>
              <span className="mt-1 block text-xs text-[#657082]">
                {template.viewKind
                  ? insightViewLabel(template.viewKind)
                  : "Insight"}
                {template.grain
                  ? ` · Analyze by ${titleCase(template.grain)}`
                  : ""}
              </span>
            </button>
          ))}
          {!templates.length ? (
            <div className="rounded-lg border border-dashed border-[#cfd8e3] p-5 text-center text-sm text-[#657082]">
              No templates are available.
            </div>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function parseTemplate(value: Record<string, unknown>): BuilderTemplate | null {
  const id = typeof value.id === "string" ? value.id : "";
  const label = typeof value.label === "string" ? value.label : "";
  if (!id || !label) return null;
  const definition = isRecord(value.definition) ? value.definition : {};
  const analysis = isRecord(definition.analysis) ? definition.analysis : {};
  const view = isRecord(definition.view) ? definition.view : {};
  const grain =
    typeof analysis.grain === "string" && isGrain(analysis.grain)
      ? analysis.grain
      : undefined;
  const viewKind =
    typeof view.kind === "string" && isInsightViewKind(view.kind)
      ? view.kind
      : undefined;
  return { id, label, grain, viewKind };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isGrain(value: string): value is InsightDraft["analysis"]["grain"] {
  return ["sample", "subject", "run", "feature", "variant", "file"].includes(
    value,
  );
}
