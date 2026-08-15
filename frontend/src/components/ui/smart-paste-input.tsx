"use client";

import * as React from "react";
import { ArrowRight, X, Paperclip, Sparkles, Activity, GitBranch, Dna, UserCircle, Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export interface PasteAttachment {
  id: string;
  content: string;
  title?: string;
  label?: string;
}

export interface SmartPasteSubmitPayload {
  text: string;
  attachments: PasteAttachment[];
}

export interface SmartPasteInputProps {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  attachments?: PasteAttachment[];
  defaultAttachments?: PasteAttachment[];
  onAttachmentsChange?: (attachments: PasteAttachment[]) => void;
  onSubmit?: (payload: SmartPasteSubmitPayload) => void;
  placeholder?: string;
  pasteThreshold?: number;
  pasteLineThreshold?: number;
  maxAttachments?: number;
  editable?: boolean;
  disabled?: boolean;
  maxInputHeight?: number;
  accentClassName?: string;
  label?: string;
  className?: string;

  // Custom VariantMind integrations
  attachedFile?: File | null;
  onAttachedFileChange?: (file: File | null) => void;
  patientLabel?: string;
  onPatientLabelChange?: (label: string) => void;
  vcfCount?: number;
  aiEnabled?: boolean;
  onAiEnabledChange?: (val: boolean) => void;
  svEnabled?: boolean;
  onSvEnabledChange?: (val: boolean) => void;
  pedEnabled?: boolean;
  onPedEnabledChange?: (val: boolean) => void;
}

const BARE_TEXTAREA =
  "w-full resize-none border-0 bg-transparent px-0 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden";

const PREVIEW_FADE = {
  maskImage: "linear-gradient(to bottom, #000 45%, transparent 100%)",
  WebkitMaskImage: "linear-gradient(to bottom, #000 45%, transparent 100%)",
} as const;

let attachmentCount = 0;

export function derivePasteTitle(content: string, fallback = "Pasted text") {
  const first = content
    .split("\n")
    .map((line) => line.trim())
    .find(Boolean);
  if (!first) return fallback;
  const clean = first
    .replace(/^#{1,6}\s+/, "")
    .replace(/^[-*+]\s+/, "")
    .trim();
  if (!clean) return fallback;
  return clean.length > 64 ? `${clean.slice(0, 63).trimEnd()}…` : clean;
}

function derivePastePreview(content: string) {
  const lines = content.split("\n");
  let i = 0;
  while (i < lines.length && !lines[i].trim()) i += 1;
  i += 1; // the title line itself
  while (i < lines.length && !lines[i].trim()) i += 1;
  const rest = lines.slice(i).join("\n").trim();
  return rest || content.trim();
}

function formatCount(count: number) {
  return `${count} ${count === 1 ? "character" : "characters"}`;
}

function useControllable<T>(
  controlled: T | undefined,
  fallback: T,
  onChange?: (value: T) => void,
) {
  const [uncontrolled, setUncontrolled] = React.useState(fallback);
  const isControlled = controlled !== undefined;
  const value = isControlled ? (controlled as T) : uncontrolled;

  const valueRef = React.useRef(value);
  valueRef.current = value;

  const setValue = React.useCallback(
    (next: T | ((prev: T) => T)) => {
      const resolved =
        typeof next === "function"
          ? (next as (prev: T) => T)(valueRef.current)
          : next;
      if (!isControlled) setUncontrolled(resolved);
      onChange?.(resolved);
    },
    [isControlled, onChange],
  );

  return [value, setValue] as const;
}

export function SmartPasteInput({
  value,
  defaultValue = "",
  onValueChange,
  attachments,
  defaultAttachments = [],
  onAttachmentsChange,
  onSubmit,
  placeholder = "Ask anything...",
  pasteThreshold = 320,
  pasteLineThreshold = 8,
  maxAttachments = 4,
  editable = true,
  disabled = false,
  maxInputHeight = 160,
  accentClassName,
  label = "Message",
  className,

  attachedFile = null,
  onAttachedFileChange,
  patientLabel = "",
  onPatientLabelChange,
  vcfCount = 0,
  aiEnabled = true,
  onAiEnabledChange,
  svEnabled = true,
  onSvEnabledChange,
  pedEnabled = false,
  onPedEnabledChange,
}: SmartPasteInputProps) {
  const [text, setText] = useControllable(value, defaultValue, onValueChange);
  const [items, setItems] = useControllable(
    attachments,
    defaultAttachments,
    onAttachmentsChange,
  );
  const [openId, setOpenId] = React.useState<string | null>(null);

  const inputRef = React.useRef<HTMLTextAreaElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const openItem = items.find((item) => item.id === openId) ?? null;
  const canSubmit = !disabled && (text.trim().length > 0 || items.length > 0 || attachedFile !== null);

  React.useLayoutEffect(() => {
    const node = inputRef.current;
    if (!node) return;
    node.style.height = "0px";
    node.style.height = `${Math.min(node.scrollHeight, maxInputHeight)}px`;
  }, [text, maxInputHeight]);

  const handlePaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    if (disabled) return;
    const pasted = event.clipboardData.getData("text/plain");
    if (!pasted) return;

    const isLong =
      pasted.length >= pasteThreshold ||
      pasted.split("\n").length >= pasteLineThreshold;
    if (!isLong || items.length >= maxAttachments) return;

    event.preventDefault();
    attachmentCount += 1;
    setItems((prev) => [
      ...prev,
      { id: `paste-${attachmentCount}`, content: pasted },
    ]);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key !== "Enter" ||
      event.shiftKey ||
      event.nativeEvent.isComposing
    )
      return;
    event.preventDefault();
    submit();
  };

  const submit = () => {
    if (!canSubmit) return;
    onSubmit?.({ text: text.trim(), attachments: items });
    setText("");
    setItems([]);
  };

  const saveAttachment = (id: string, content: string) => {
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, content } : item)),
    );
    setOpenId(null);
  };

  const removeAttachment = (id: string) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
    setOpenId(null);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    onAttachedFileChange?.(file);
    e.target.value = "";
  };

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  const filesRemaining = 3 - vcfCount;
  const atFileLimit = filesRemaining <= 0;

  return (
    <div className={cn("w-full max-w-[720px] mx-auto", className)}>
      <div
        className={cn(
          "rounded-[24px] border border-slate-800 bg-slate-950/75 backdrop-blur-xl p-2 shadow-2xl overflow-hidden",
          disabled && "opacity-60",
        )}
      >
        {/* Unified Attachment Area */}
        {(items.length > 0 || attachedFile) && (
          <div className="flex flex-wrap gap-3 px-3 pb-3 pt-2 border-b border-slate-900 bg-slate-900/10 mb-2">
            {/* Paste Attachments */}
            {items.map((item) => (
              <AttachmentCard
                key={item.id}
                attachment={item}
                disabled={disabled}
                onOpen={() => setOpenId(item.id)}
                onRemove={() => removeAttachment(item.id)}
              />
            ))}

            {/* VCF File Attachment */}
            {attachedFile && (
              <div className="group relative">
                <div className="flex h-[104px] w-[256px] flex-col justify-between overflow-hidden rounded-2xl border border-indigo-500/40 bg-indigo-950/20 px-4 py-3 text-left shadow-sm">
                  <span className="w-full truncate text-[14px] font-semibold text-indigo-200 flex items-center gap-1.5">
                    <Dna className="w-4 h-4 text-indigo-400 shrink-0" />
                    <span className="truncate">{attachedFile.name}</span>
                  </span>
                  <div className="flex items-center gap-1.5 mt-2">
                    <UserCircle size={14} className="text-slate-400 shrink-0" />
                    <input
                      type="text"
                      placeholder="Patient label (e.g. Proband)"
                      value={patientLabel}
                      onChange={(e) => onPatientLabelChange?.(e.target.value)}
                      className="border border-slate-800 rounded-lg px-2 py-0.5 text-[11px] bg-slate-950 text-slate-100 placeholder:text-slate-500 outline-none w-full focus:border-slate-700"
                    />
                  </div>
                </div>
                <Button
                  size="icon"
                  variant="outline"
                  onClick={() => onAttachedFileChange?.(null)}
                  className="absolute -right-1.5 -top-1.5 size-6 rounded-full bg-slate-900 border-slate-800 p-0 text-slate-400 hover:text-white shadow-sm"
                >
                  <X className="size-3.5" />
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Textarea Row */}
        <div className="flex items-end gap-2 pl-4 pr-2">
          <Textarea
            ref={inputRef}
            rows={1}
            value={text}
            disabled={disabled}
            aria-label={label}
            placeholder={placeholder}
            onPaste={handlePaste}
            onKeyDown={handleKeyDown}
            onChange={(event) => setText(event.target.value)}
            className={cn(
              BARE_TEXTAREA,
              "min-h-[48px] flex-1 py-[11px] pr-2",
              "text-[15px] leading-[22px] tracking-[-0.01em] text-slate-100",
              "placeholder:text-slate-400/70",
            )}
            style={{ maxHeight: maxInputHeight }}
          />
        </div>

        {/* Footer controls row */}
        <div className="flex items-center justify-between px-3 py-2 mt-2 border-t border-slate-900/50 bg-slate-900/5">
          {/* Paperclip + Toggles */}
          <div className="flex items-center gap-1.5">
            {/* Paperclip file uploader */}
            <button
              type="button"
              onClick={triggerFileInput}
              disabled={disabled || atFileLimit}
              className={cn(
                "p-2 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors relative shrink-0",
                atFileLimit && "opacity-50 cursor-not-allowed"
              )}
              title={
                atFileLimit
                  ? "Max 3 VCF files per conversation"
                  : `Attach VCF file (${filesRemaining} remaining)`
              }
            >
              <Paperclip className="w-4 h-4" />
              {vcfCount > 0 && (
                <span className="absolute -top-1.5 -right-1.5 bg-indigo-600 text-white rounded-full w-4 h-4 text-[8px] flex items-center justify-center font-bold border border-slate-950">
                  {vcfCount}
                </span>
              )}
            </button>
            <input
              id="vcf-file-input"
              type="file"
              ref={fileInputRef}
              accept=".vcf,.vcf.gz,.txt"
              onChange={handleFileUpload}
              disabled={disabled || atFileLimit}
              className="hidden"
            />

            <div className="h-4 w-px bg-slate-800 mx-1 shrink-0" />

            {/* AI Toggle */}
            <ToggleButton
              active={aiEnabled}
              onClick={() => onAiEnabledChange?.(!aiEnabled)}
              icon={<Sparkles className="w-3.5 h-3.5" />}
              label="AI Copilot"
              title="Toggle AI Copilot"
            />
            {/* SV Toggle */}
            <ToggleButton
              active={svEnabled}
              onClick={() => onSvEnabledChange?.(!svEnabled)}
              icon={<Activity className="w-3.5 h-3.5" />}
              label="Single Variant"
              title="Toggle Single Variant Deep Analysis"
            />
            {/* Pedigree Toggle */}
            <ToggleButton
              active={pedEnabled}
              onClick={() => onPedEnabledChange?.(!pedEnabled)}
              icon={<GitBranch className="w-3.5 h-3.5" />}
              label="Pedigree Tool"
              title="Toggle Pedigree Generation"
            />
          </div>

          {/* Send/Analyze Button */}
          <Button
            onClick={submit}
            disabled={!canSubmit}
            aria-label="Send message"
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 rounded-xl transition-all duration-300 text-xs font-semibold shrink-0 h-9",
              canSubmit
                ? cn(
                    accentClassName || "bg-blue-600 text-white hover:bg-blue-500",
                    "shadow-lg shadow-blue-500/25 active:scale-95",
                  )
                : "bg-slate-800 text-slate-500 cursor-not-allowed disabled:opacity-100",
            )}
          >
            {disabled ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Send className="w-3.5 h-3.5" />
            )}
            <span>Analyze</span>
          </Button>
        </div>
      </div>

      <AttachmentEditor
        attachment={openItem}
        editable={editable}
        accentClassName={accentClassName || "bg-blue-600 text-white hover:bg-blue-500"}
        onClose={() => setOpenId(null)}
        onSave={saveAttachment}
        onRemove={removeAttachment}
      />
    </div>
  );
}

interface ToggleButtonProps {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  title: string;
}

function ToggleButton({ active, onClick, icon, label, title }: ToggleButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        // Fixed height so the toggles line up with the paperclip and the send
        // button instead of sitting slightly high in the row.
        "flex h-7 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-medium transition-colors duration-200",
        active
          ? "border-blue-500/30 bg-blue-500/10 text-blue-200"
          : "border-slate-800/70 bg-transparent text-slate-500 hover:border-slate-700 hover:text-slate-300"
      )}
      title={title}
      aria-pressed={active}
    >
      {icon}
      <span className="hidden lg:inline">{label}</span>
    </button>
  );
}

function AttachmentCard({
  attachment,
  disabled,
  onOpen,
  onRemove,
}: {
  attachment: PasteAttachment;
  disabled?: boolean;
  onOpen: () => void;
  onRemove: () => void;
}) {
  const title = attachment.title ?? derivePasteTitle(attachment.content);
  const preview = React.useMemo(
    () => derivePastePreview(attachment.content),
    [attachment.content],
  );

  return (
    <div className="group relative">
      <button
        type="button"
        onClick={onOpen}
        disabled={disabled}
        aria-label={`Open attachment: ${title}`}
        className={cn(
          "flex h-[104px] w-[256px] flex-col overflow-hidden rounded-2xl",
          "border border-slate-800 bg-slate-950/60 px-4 py-3 text-left shadow-sm",
          "transition-all duration-200 ease-out",
          "hover:-translate-y-px hover:border-slate-700 hover:shadow-md",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
          "disabled:pointer-events-none",
        )}
      >
        <span className="w-full truncate text-[14px] font-semibold tracking-[-0.01em] text-slate-100">
          {title}
        </span>
        <span
          className="mt-1 flex-1 overflow-hidden whitespace-pre-wrap break-words text-[11px] leading-[1.5] text-slate-400"
          style={PREVIEW_FADE}
        >
          {preview}
        </span>
      </button>

      <Button
        size="icon"
        variant="outline"
        onClick={onRemove}
        disabled={disabled}
        aria-label={`Remove attachment: ${title}`}
        className={cn(
          "absolute -right-1.5 -top-1.5 size-6 rounded-full bg-slate-900 border-slate-800 p-0 text-slate-400 hover:text-white shadow-sm",
          "transition-opacity duration-150 sm:opacity-0",
          "sm:group-hover:opacity-100 sm:focus-visible:opacity-100",
        )}
      >
        <X className="size-3.5" strokeWidth={2.25} />
      </Button>
    </div>
  );
}

function AttachmentEditor({
  attachment,
  editable,
  accentClassName,
  onClose,
  onSave,
  onRemove,
}: {
  attachment: PasteAttachment | null;
  editable: boolean;
  accentClassName: string;
  onClose: () => void;
  onSave: (id: string, content: string) => void;
  onRemove: (id: string) => void;
}) {
  const [draft, setDraft] = React.useState("");
  const [overflow, setOverflow] = React.useState({ top: false, bottom: false });
  const [snapshot, setSnapshot] = React.useState<PasteAttachment | null>(null);

  const editorRef = React.useRef<HTMLTextAreaElement>(null);
  const open = attachment !== null;

  React.useLayoutEffect(() => {
    if (!attachment) return;
    setSnapshot(attachment);
    setDraft(attachment.content);
  }, [attachment]);

  const syncOverflow = React.useCallback(() => {
    const node = editorRef.current;
    if (!node) return;
    setOverflow({
      top: node.scrollTop > 2,
      bottom: node.scrollTop + node.clientHeight < node.scrollHeight - 2,
    });
  }, []);

  const active = attachment ?? snapshot;
  const heading = active?.label ?? "Pasted text";
  const canSave = editable && draft.trim().length > 0;

  const commit = () => {
    if (!active) return;
    if (!editable) return onClose();
    if (!canSave) return;
    onSave(active.id, draft);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      {active && (
        <DialogContent
          className={cn(
            "gap-0 rounded-[26px] border-slate-800 bg-slate-900 text-slate-100 px-7 pb-5 pt-6",
            "sm:max-w-[600px]",
            "[&>button]:hidden",
          )}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            const node = editorRef.current;
            if (!node) return;
            node.focus();
            node.setSelectionRange(0, 0);
            node.scrollTop = 0;
            syncOverflow();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
              event.preventDefault();
              commit();
            }
          }}
        >
          <DialogHeader className="flex-row items-baseline justify-between gap-4 space-y-0">
            <DialogTitle className="text-[19px] tracking-[-0.01em] text-slate-100">
              {heading}
            </DialogTitle>
            <DialogDescription className="shrink-0 text-[14px] tabular-nums text-slate-400">
              {formatCount(draft.length)}
            </DialogDescription>
          </DialogHeader>

          <div className="relative mt-4 border border-slate-800 rounded-lg p-2 bg-slate-950">
            <Textarea
              ref={editorRef}
              value={draft}
              readOnly={!editable}
              spellCheck={false}
              onScroll={syncOverflow}
              aria-label={`${heading} content`}
              onChange={(event) => {
                setDraft(event.target.value);
                syncOverflow();
              }}
              className={cn(
                BARE_TEXTAREA,
                "h-[300px] max-h-[45vh] py-0 text-slate-100",
                "font-mono text-[14px] leading-[1.85]",
              )}
            />

            <div
              aria-hidden
              className={cn(
                "pointer-events-none absolute inset-x-0 top-0 h-8",
                "bg-gradient-to-b from-slate-950 to-transparent transition-opacity duration-200",
                overflow.top ? "opacity-100" : "opacity-0",
              )}
            />
            <div
              aria-hidden
              className={cn(
                "pointer-events-none absolute inset-x-0 bottom-0 h-20",
                "bg-gradient-to-t from-slate-950 via-slate-950/85 to-transparent transition-opacity duration-200",
                overflow.bottom ? "opacity-100" : "opacity-0",
              )}
            />
          </div>

          <DialogFooter className="mt-4 flex-row items-center justify-between sm:justify-between">
            <Button
              variant="ghost"
              onClick={() => onRemove(active.id)}
              className="-ml-3 text-[14px] font-normal text-slate-400 hover:text-slate-100 hover:bg-slate-850"
            >
              Remove
            </Button>

            <Button
              onClick={commit}
              disabled={editable && !canSave}
              className={cn(
                "h-auto rounded-full px-6 py-2.5 text-[14px] shadow-sm font-semibold",
                "transition-all duration-200 ease-out hover:scale-[1.02] active:scale-[0.98]",
                accentClassName,
              )}
            >
              {editable ? "Save" : "Close"}
            </Button>
          </DialogFooter>
        </DialogContent>
      )}
    </Dialog>
  );
}
