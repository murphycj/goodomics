import { useMutation } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  ArrowUp,
  Bot,
  ChevronsRight,
  FileText,
  GripVertical,
  Sparkles,
  User,
} from "lucide-react";
import type { RefObject } from "react";
import { useEffect, useRef, useState } from "react";
import type { AiMessage, AiToolEvidence } from "../../api";
import { askAi } from "../../api";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";

type TranscriptMessage = AiMessage & {
  toolCalls?: AiToolEvidence[];
};

export function AskAiSidePanel({
  defaultProjectId,
  defaultProjectName,
  draft,
  draftNonce,
  onClose,
  open,
  setWidth,
  width,
}: {
  defaultProjectId?: string;
  defaultProjectName?: string;
  draft: string;
  draftNonce: number;
  onClose: () => void;
  open: boolean;
  setWidth: (width: number) => void;
  width: number;
}) {
  const [chatDraft, setChatDraft] = useState("");
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const dragStart = useRef<{ startX: number; startWidth: number } | null>(null);

  const chat = useMutation({
    mutationFn: (nextMessages: AiMessage[]) =>
      askAi({
        conversationId,
        messages: nextMessages,
        projectId: defaultProjectId,
      }),
    onSuccess: (response) => {
      setConversationId(response.conversation_id);
      setMessages((current) => [
        ...current,
        {
          ...response.message,
          toolCalls: response.tool_calls,
        },
      ]);
    },
  });

  useEffect(() => {
    if (!open) return;
    if (draft.trim()) setChatDraft(draft);
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, [draft, draftNonce, open]);

  useEffect(() => {
    if (!open || messages.length === 0) return;
    const frame = requestAnimationFrame(() => {
      bottomRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
    });
    return () => cancelAnimationFrame(frame);
  }, [chat.error, chat.isPending, messages.length, open]);

  useEffect(() => {
    const onPointerMove = (event: PointerEvent) => {
      if (!dragStart.current) return;
      const nextWidth = dragStart.current.startWidth + dragStart.current.startX - event.clientX;
      const maxWidth = Math.min(window.innerWidth - 72, 760);
      setWidth(Math.max(360, Math.min(maxWidth, nextWidth)));
    };
    const onPointerUp = () => {
      dragStart.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [setWidth]);

  const submitChat = (selectedPrompt?: string) => {
    const content = (selectedPrompt ?? chatDraft).trim();
    if (!content || chat.isPending) return;
    const userMessage: TranscriptMessage = { role: "user", content };
    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setChatDraft("");
    chat.mutate(nextMessages.map(({ role, content }) => ({ role, content })));
  };

  return (
    <aside
      aria-hidden={!open}
      className={cn(
        "fixed bottom-0 right-0 top-0 z-40 grid max-w-[calc(100vw-1rem)] grid-rows-[auto_1fr_auto] border-l border-[#2c2c2c] bg-[#242424] text-[#f3f3f3] shadow-[-18px_0_50px_rgb(0_0_0/0.22)]",
        "transition-transform duration-200 ease-out",
        open ? "translate-x-0" : "pointer-events-none translate-x-full",
      )}
      style={{ width }}
    >
      <div
        aria-hidden="true"
        className="absolute bottom-0 left-[-7px] top-0 hidden w-3 cursor-col-resize items-center justify-center text-[#8e959d] hover:text-[#d8dde5] md:flex"
        onPointerDown={(event) => {
          dragStart.current = { startX: event.clientX, startWidth: width };
          document.body.style.cursor = "col-resize";
          document.body.style.userSelect = "none";
        }}
      >
        <GripVertical size={16} />
      </div>
      <div className="flex min-h-[64px] items-center justify-between gap-3 border-b border-[#353535] px-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[#e8f8ef] text-[#102017]">
            <Sparkles size={17} />
          </span>
          <div className="min-w-0">
            <div className="font-semibold">Ask AI</div>
            <div className="truncate text-xs text-[#aeb4bd]">
              {defaultProjectName
                ? `Grounded in ${defaultProjectName}`
                : "Grounded in Goodomics data"}
            </div>
            <div className="truncate text-[0.68rem] text-[#858c95]">
              Read-only. AI cannot modify data.
            </div>
          </div>
        </div>
        <Button
          aria-label="Hide Ask AI"
          className="border-[#444444] bg-[#2d2d2d] text-[#cfcfcf] hover:border-[#565656] hover:bg-[#333333] hover:text-white"
          onClick={onClose}
          size="icon"
          type="button"
          variant="outline"
        >
          <ChevronsRight size={16} />
        </Button>
      </div>
      <div className="overflow-auto px-4 py-4">
        {messages.length === 0 ? null : (
          <div className="grid gap-4">
            {messages.map((message, index) => (
              <ChatBubble key={`${message.role}-${index}`} message={message} />
            ))}
            {chat.isPending && (
              <div className="flex items-center gap-2 text-sm text-[#aeb4bd]">
                <Bot size={16} />
                Thinking with Goodomics tools...
              </div>
            )}
          </div>
        )}
        {chat.error instanceof Error && (
          <div className="mt-4 rounded-[7px] border border-[#7f2c22] bg-[#351d19] px-3 py-2 text-sm text-[#ffb4a8]">
            {chat.error.message}
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="px-4 pb-3">
        {messages.length === 0 && (
          <ExampleList
            examples={examplePrompts()}
            onExampleSelect={submitChat}
          />
        )}
        <ChatComposer
          chatDraft={chatDraft}
          disabled={chat.isPending}
          onDraftChange={setChatDraft}
          onSubmit={submitChat}
          textareaRef={textareaRef}
        />
      </div>
    </aside>
  );
}

function ExampleList({
  examples,
  onExampleSelect,
}: {
  examples: string[];
  onExampleSelect: (example: string) => void;
}) {
  return (
    <div className="mb-5 grid gap-3">
      <div className="text-2xl font-semibold text-[#f3f3f3]">
        How can I assist you?
      </div>
      <div className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-[#8f969f]">
        Ideas
      </div>
      {examples.map((example) => (
        <button
          className="flex cursor-pointer items-center gap-3 rounded-[7px] px-1 py-1.5 text-left text-sm text-[#d8dde5] transition-colors hover:bg-[#303030] hover:text-white"
          key={example}
          onClick={() => onExampleSelect(example)}
          type="button"
        >
          <FileText className="shrink-0 text-[#aeb4bd]" size={17} />
          <span>{example}</span>
        </button>
      ))}
    </div>
  );
}

function ChatComposer({
  chatDraft,
  disabled,
  onDraftChange,
  onSubmit,
  textareaRef,
}: {
  chatDraft: string;
  disabled: boolean;
  onDraftChange: (draft: string) => void;
  onSubmit: () => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto] gap-2 rounded-[8px] border border-[#444444] bg-[#1d1d1d] p-2">
      <textarea
        ref={textareaRef}
        className="max-h-[160px] min-h-[64px] resize-none border-0 bg-transparent px-2 py-1.5 text-sm leading-6 text-[#f3f3f3] outline-none placeholder:text-[#7f858d]"
        onChange={(event) => onDraftChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            onSubmit();
          }
        }}
        placeholder="Ask a question about projects, runs, samples, files, or metrics..."
        value={chatDraft}
      />
      <Button
        aria-label="Send Ask AI message"
        className="mt-auto h-9 w-9 border-[#58c98a] bg-[#e8f8ef] text-[#102017] hover:bg-white"
        disabled={!chatDraft.trim() || disabled}
        onClick={onSubmit}
        size="icon"
        type="button"
        variant="outline"
      >
        <ArrowUp size={16} />
      </Button>
    </div>
  );
}

function ChatBubble({ message }: { message: TranscriptMessage }) {
  const isUser = message.role === "user";
  return (
    <div
      className={cn(
        "grid gap-2",
        isUser ? "justify-items-end" : "justify-items-start",
      )}
    >
      <div
        className={cn(
          "grid min-w-0 max-w-[92%] gap-2 rounded-[8px] px-3 py-2 text-sm leading-6",
          isUser
            ? "bg-[#e8f8ef] text-[#102017]"
            : "border border-[#353535] bg-[#202020] text-[#d8dde5]",
        )}
      >
        <div className="flex items-center gap-2 text-xs font-semibold">
          {isUser ? <User size={14} /> : <Bot size={14} />}
          {isUser ? "You" : "Goodomics AI"}
        </div>
        <div className="min-w-0 whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
          <MessageContent content={message.content} toolCalls={message.toolCalls ?? []} />
        </div>
      </div>
      {!isUser && message.toolCalls && message.toolCalls.length > 0 && (
        <div className="flex max-w-[92%] flex-wrap gap-1.5">
          {message.toolCalls.map((tool, index) => (
            <span
              className="rounded-full border border-[#3d4f44] bg-[#203028] px-2 py-1 text-[0.72rem] text-[#bfe8cf]"
              key={`${tool.name}-${index}`}
            >
              {tool.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function MessageContent({
  content,
  toolCalls,
}: {
  content: string;
  toolCalls: AiToolEvidence[];
}) {
  const entityLinks = entityLinksFromToolCalls(toolCalls);
  return (
    <>
      {markdownLinkSegments(content).map((segment, index) => {
        if (segment.kind === "text") {
          return plainTextLinkSegments(segment.text, entityLinks).map((textSegment, textIndex) => {
            if (textSegment.kind === "text") return textSegment.text;
            return (
              <ChatLink
                href={textSegment.href}
                key={`${textSegment.href}-${index}-${textIndex}`}
                label={textSegment.label}
              />
            );
          });
        }
        return (
          <ChatLink
            href={segment.href}
            key={`${segment.href}-${index}`}
            label={segment.label}
          />
        );
      })}
    </>
  );
}

function ChatLink({ href, label }: { href: string; label: string }) {
  const encodedHref = href.replaceAll(" ", "%20");
  if (encodedHref.startsWith("/")) {
    return (
      <Link
        className="font-medium text-[#74d99f] underline underline-offset-2 [overflow-wrap:anywhere] hover:text-[#a9efc4]"
        to={encodedHref}
      >
        {label}
      </Link>
    );
  }
  return (
    <a
      className="font-medium text-[#74d99f] underline underline-offset-2 [overflow-wrap:anywhere] hover:text-[#a9efc4]"
      href={encodedHref}
      rel="noreferrer"
      target="_blank"
    >
      {label}
    </a>
  );
}

function markdownLinkSegments(content: string) {
  const segments: Array<
    | { kind: "text"; text: string }
    | { href: string; kind: "link"; label: string }
  > = [];
  const pattern = /\[([^\]\n]+)\]\(([^)\n]+)\)/g;
  let lastIndex = 0;
  for (const match of content.matchAll(pattern)) {
    if (match.index > lastIndex) {
      segments.push({ kind: "text", text: content.slice(lastIndex, match.index) });
    }
    segments.push({ kind: "link", label: match[1], href: match[2].trim() });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < content.length) {
    segments.push({ kind: "text", text: content.slice(lastIndex) });
  }
  return segments.length ? segments : [{ kind: "text" as const, text: content }];
}

function plainTextLinkSegments(content: string, links: Map<string, string>) {
  const labels = [...links.keys()].sort((left, right) => right.length - left.length);
  if (labels.length === 0) return [{ kind: "text" as const, text: content }];

  const segments: Array<
    | { kind: "text"; text: string }
    | { href: string; kind: "link"; label: string }
  > = [];
  const pattern = new RegExp(
    `(?<![A-Za-z0-9_%/-])(${labels.map(escapeRegExp).join("|")})(?![A-Za-z0-9_%/-])`,
    "gi",
  );
  let lastIndex = 0;
  for (const match of content.matchAll(pattern)) {
    if (match.index > lastIndex) {
      segments.push({ kind: "text", text: content.slice(lastIndex, match.index) });
    }
    const label = match[0];
    const href = links.get(label.toLowerCase());
    if (href) {
      segments.push({ kind: "link", label, href });
    } else {
      segments.push({ kind: "text", text: label });
    }
    lastIndex = match.index + label.length;
  }
  if (lastIndex < content.length) {
    segments.push({ kind: "text", text: content.slice(lastIndex) });
  }
  return segments.length ? segments : [{ kind: "text" as const, text: content }];
}

function entityLinksFromToolCalls(toolCalls: AiToolEvidence[]) {
  const links = new Map<string, string>();
  const conflicts = new Set<string>();

  const addLink = (label: unknown, path: string) => {
    if (typeof label !== "string") return;
    const cleanLabel = label.trim();
    if (cleanLabel.length < 2) return;
    const key = cleanLabel.toLowerCase();
    if (conflicts.has(key)) return;
    const existing = links.get(key);
    if (existing && existing !== path) {
      links.delete(key);
      conflicts.add(key);
      return;
    }
    links.set(key, path);
  };

  const visit = (value: unknown) => {
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (!value || typeof value !== "object") return;
    const record = value as Record<string, unknown>;
    const appPath = record.app_path;
    if (typeof appPath === "string" && appPath.startsWith("/")) {
      for (const label of entityLabels(record)) {
        addLink(label, appPath);
      }
    }
    Object.values(record).forEach(visit);
  };

  toolCalls.forEach((toolCall) => visit(toolCall.result));
  return links;
}

function entityLabels(record: Record<string, unknown>) {
  if ("sample_id" in record) return [record.sample_name, record.sample_id];
  if ("run_id" in record) return [record.name, record.run_id];
  if ("project_id" in record) return [record.name, record.project_id, record.slug];
  return [];
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function examplePrompts() {
  return [
    "What are the most recent runs for this project?",
    "List the samples in this project.",
    "List the projects in this Goodomics database.",
    "Which files were attached to the latest run?",
    "Show mapping metrics for run-1.",
  ];
}
