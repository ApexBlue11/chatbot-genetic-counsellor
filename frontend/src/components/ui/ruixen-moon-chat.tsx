"use client";

import React, { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Loader2, Dna, GitBranch, Activity, Upload } from "lucide-react";
import api from "../../services/api";
import MessageBubble from "../MessageBubble";
import ThinkingIndicator from "../ThinkingIndicator";
import { SmartPasteInput, type PasteAttachment, derivePasteTitle } from "./smart-paste-input";

interface RuixenMoonChatProps {
  activeConversation: string | null;
  onChatUpdated: () => void;
}

export default function RuixenMoonChat({ activeConversation, onChatUpdated }: RuixenMoonChatProps) {
  const [messages, setMessages] = useState<any[]>([]);
  const [message, setMessage] = useState("");
  const [pasteAttachments, setPasteAttachments] = useState<PasteAttachment[]>([]);
  const [loading, setLoading] = useState(false);
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [patientLabel, setPatientLabel] = useState("");
  const [vcfCount, setVcfCount] = useState(0);
  const [uploadError, setUploadError] = useState("");

  // Toggles
  const [aiEnabled, setAiEnabled] = useState(true);
  const [svEnabled, setSvEnabled] = useState(true);
  const [pedEnabled, setPedEnabled] = useState(false);
  // Thinking mode is a preference about how you want to be answered, not a
  // property of one conversation — someone who wants the reasoning shown
  // wants it on the next question too, and after a reload.
  const [thinkingEnabled, setThinkingEnabled] = useState(
    () => localStorage.getItem("vm_thinking") === "1"
  );

  useEffect(() => {
    localStorage.setItem("vm_thinking", thinkingEnabled ? "1" : "0");
  }, [thinkingEnabled]);

  const endOfMessagesRef = useRef<HTMLDivElement>(null);
  const currentConvRef = useRef<string | null>(activeConversation);

  useEffect(() => {
    currentConvRef.current = activeConversation;
    if (activeConversation) {
      loadMessages(activeConversation);
      setVcfCount(0);
      setUploadError("");
      setAttachedFile(null);
      setPatientLabel("");
      setMessage("");
      setPasteAttachments([]);
    } else {
      setMessages([]);
    }
  }, [activeConversation]);

  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const loadMessages = async (id: string) => {
    try {
      const msgs = await api.getMessages(id);
      setMessages(msgs);
      // Infer VCF count from existing messages
      const uploadCount = msgs.filter(
        (m: any) => m.role === "user" && m.content?.startsWith("📎 Uploaded")
      ).length;
      setVcfCount(uploadCount);
    } catch (err) {
      console.error("Failed to load messages", err);
    }
  };

  const handleSmartSubmit = async (payload: { text: string; attachments: PasteAttachment[] }) => {
    const { text, attachments } = payload;
    if ((!text.trim() && attachments.length === 0 && !attachedFile) || !activeConversation) return;

    // Format final message to include the document content if any attachments are present
    let userMsg = text.trim();
    if (attachments.length > 0) {
      const attachmentsText = attachments
        .map((att) => {
          const title = att.title || derivePasteTitle(att.content);
          return `### Attached Document: ${title}\n\`\`\`\n${att.content}\n\`\`\``;
        })
        .join("\n\n");
      userMsg = `${attachmentsText}\n\n${text}`.trim() || "Please analyze the attached document(s).";
    } else if (userMsg === "" && attachedFile) {
      userMsg = `Please analyze VCF file: ${attachedFile.name}`;
    }

    const reqConv = activeConversation;
    const fileToSend = attachedFile;
    const labelToSend = patientLabel.trim() || `Patient-${vcfCount + 1}`;

    setMessage("");
    setPasteAttachments([]);
    setAttachedFile(null);
    setPatientLabel("");
    setUploadError("");
    setLoading(true);

    try {
      if (fileToSend) {
        // Show user message immediately
        setMessages((prev) => [
          ...prev,
          {
            role: "user",
            content: `📎 Uploaded \`${fileToSend.name}\` (Patient: **${labelToSend}**)\n\n${userMsg}`,
          },
        ]);

        let uploadRes;
        try {
          uploadRes = await api.uploadVcf(reqConv, fileToSend, labelToSend);
        } catch (uploadErr: any) {
          setUploadError(uploadErr.message || "Upload failed");
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: `⚠️ **Upload failed:** ${uploadErr.message}`,
            },
          ]);
          return;
        }

        if (currentConvRef.current !== reqConv) return;

        setVcfCount(uploadRes.total_vcf_count || vcfCount + 1);

        const summaryMsg = {
          role: "assistant",
          content: uploadRes.summary,
          metadata: { type: "vcf_analysis", ...uploadRes },
        };
        setMessages((prev) => [...prev, summaryMsg]);

        const contextMode = uploadRes.context_mode || "basic";
        const systemContext =
          contextMode === "deep"
            ? `[VCF uploaded for patient '${labelToSend}'. Deep context mode: full annotations loaded server-side.]`
            : `[VCF uploaded for patient '${labelToSend}'. Basic context mode: ${uploadRes.summary}. Use read_enriched_data tool to drill into specific variants.]`;

        if (aiEnabled) {
          const res = await api.sendMessage(
            reqConv,
            userMsg,
            true,
            svEnabled,
            pedEnabled,
            systemContext,
            thinkingEnabled
          );
          if (currentConvRef.current !== reqConv) return;
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: res.response, metadata: res.metadata },
          ]);
        }
      } else {
        setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
        if (aiEnabled) {
          const res = await api.sendMessage(
            reqConv,
            userMsg,
            true,
            svEnabled,
            pedEnabled,
            null,
            thinkingEnabled
          );
          if (currentConvRef.current !== reqConv) return;
          setMessages((prev) => [
            ...prev,
            { role: "assistant", content: res.response, metadata: res.metadata },
          ]);
        }
      }
      onChatUpdated();
    } catch (err: any) {
      console.error(err);
      if (currentConvRef.current !== reqConv) return;
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Error: ${err.message || "Connection failed"}`,
        },
      ]);
    } finally {
      if (currentConvRef.current === reqConv) setLoading(false);
    }
  };

  const handleQuickAction = (text: string) => {
    if (text.startsWith("Upload")) {
      document.getElementById("vcf-file-input")?.click();
    } else {
      setMessage(text);
    }
  };

  if (!activeConversation) {
    return (
      <div
        className="relative flex h-full w-full flex-col items-center justify-center bg-cover bg-center text-white"
        style={{ backgroundImage: "url('/chat-backdrop.webp')" }}
      >
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-[#1a3379]/35 via-[#0f172a]/45 to-black/75" />
        <div className="relative max-w-sm rounded-2xl border border-slate-800/80 bg-slate-950/60 p-8 text-center shadow-2xl shadow-black/40 backdrop-blur-md">
          <Dna className="mx-auto mb-4 h-10 w-10 text-blue-400" />
          <h2 className="text-xl font-bold text-slate-100">No conversation open</h2>
          <p className="mt-2 text-sm leading-relaxed text-slate-400">
            Pick one from the sidebar, or start a new conversation.
          </p>
        </div>
      </div>
    );
  }

  const displayMessages = messages.filter((m) => m.role !== "system");
  const isNewChat = displayMessages.length === 0;

  return (
    <div
      className="relative flex h-screen w-full flex-col items-center overflow-hidden bg-cover bg-center text-white"
      style={{ backgroundImage: "url('/chat-backdrop.webp')", backgroundAttachment: "fixed" }}
    >
      {/* The backdrop is served from public/ rather than a third-party CDN, and
          re-encoded from a 5.6 MB PNG to a 25 kB WebP — same image, no external
          dependency on every page load.
          The backdrop itself is left sharp: blurring it AND then floating
          near-opaque cards on top wasted the image twice over. The frosting
          now lives on the message bubbles, so the photograph reads clearly
          between them and softens only where text sits on it. */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-[#1a3379]/35 via-[#0f172a]/45 to-black/75" />

      {/* Header — inner content shares the message column's width so the logo
          lines up with the conversation instead of floating at the far edge. */}
      <header className="relative z-10 w-full border-b border-white/10 bg-slate-950/40 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-4">
          <div className="flex items-center gap-2.5">
            <div className="rounded-lg bg-gradient-to-tr from-blue-600 to-indigo-600 p-1.5 shadow-lg shadow-indigo-500/20">
              <Dna className="h-4 w-4 text-white" />
            </div>
            <h2 className="text-sm font-semibold tracking-tight text-white">VariantMind</h2>
          </div>
          {vcfCount > 0 && (
            <span className="rounded-full border border-indigo-500/40 bg-indigo-500/15 px-2.5 py-1 text-[11px] font-medium text-indigo-200">
              {vcfCount} VCF{vcfCount > 1 ? "s" : ""}
            </span>
          )}
        </div>
      </header>

      {/* Messages area or empty state */}
      {isNewChat ? (
        // pb reserves the composer's height: the composer is absolutely
        // positioned, so without it the empty state centres behind the input
        // and collides with it on short or narrow viewports.
        <div className="relative z-10 flex w-full flex-1 flex-col items-center justify-center overflow-y-auto px-4 pb-56 sm:pb-48">
          <div className="animate-fade-in max-w-md text-center">
            <div className="mb-5 inline-flex items-center justify-center rounded-2xl border border-white/10 bg-white/5 p-3.5 backdrop-blur-md">
              <Dna className="h-8 w-8 text-blue-400" />
            </div>
            <h1 className="text-3xl font-bold tracking-tight text-white">
              What are we looking at?
            </h1>
            <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-slate-400">
              Enter a variant, attach a VCF, or describe a family history.
            </p>
          </div>
        </div>
      ) : (
        <div className="scrollbar-thin scrollbar-thumb-slate-800 relative z-10 w-full flex-1 overflow-y-auto px-4 py-6">
          <div className="mx-auto max-w-4xl space-y-4 pb-[24vh]">
            {displayMessages.map((msg, idx) => (
              <div
                key={idx}
                className={cn(
                  // Translucent + heavily frosted: the backdrop stays visible
                  // through the bubble, just blurred enough to keep text crisp.
                  // Both turns are the same frosted glass. The user bubble used
                  // to be a flat blue-500/15 wash, which read as an opaque
                  // panel next to the assistant's frost instead of a sibling
                  // of it; the blue now lives in the tint and the edge, and
                  // the side of the column still says who is speaking.
                  "rounded-2xl border p-5 backdrop-blur-xl transition-all duration-300",
                  msg.role === "user"
                    ? "ml-auto max-w-[85%] border-blue-300/20 bg-blue-950/40 shadow-lg shadow-black/30"
                    : "mr-auto max-w-[92%] border-white/10 bg-slate-950/40 shadow-lg shadow-black/30"
                )}
              >
                <MessageBubble message={msg} />
              </div>
            ))}
            {loading && (
              <div className="mr-auto flex max-w-[92%] items-center rounded-2xl border border-white/10 bg-slate-950/40 p-5 shadow-lg shadow-black/30 backdrop-blur-xl">
                <ThinkingIndicator deep={thinkingEnabled} />
              </div>
            )}
            <div ref={endOfMessagesRef} />
          </div>
        </div>
      )}

      {/* Composer. The fade must span the full width while the controls stay in
          the message column — setting left/right *and* a width on one element
          over-constrains it, so `mx-auto` is ignored and the whole bar sticks
          to the left edge with a visible seam where its gradient stops. */}
      <div className="absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-black via-black/85 to-transparent pb-5 pt-8">
        <div className="mx-auto w-full max-w-4xl px-4">
        {/* Three starting points, on one line. Five wrapped onto two rows and
            buried the input underneath them. */}
        {isNewChat && (
          <div className="mb-3 flex flex-wrap items-center justify-center gap-2">
            <QuickAction
              icon={<Upload className="h-3.5 w-3.5" />}
              label="Upload VCF"
              onClick={() => handleQuickAction("Upload")}
            />
            <QuickAction
              icon={<GitBranch className="h-3.5 w-3.5" />}
              label="Draw a pedigree"
              onClick={() =>
                handleQuickAction(
                  "Draw pedigree: Proband (male, affected), Sibling (female, unaffected), Mother (affected), Father (unaffected)"
                )
              }
            />
            <QuickAction
              icon={<Activity className="h-3.5 w-3.5" />}
              label="Analyse a variant"
              onClick={() => handleQuickAction("Analyze variant rs34764978")}
            />
          </div>
        )}

        <SmartPasteInput
          value={message}
          onValueChange={setMessage}
          attachments={pasteAttachments}
          onAttachmentsChange={setPasteAttachments}
          attachedFile={attachedFile}
          onAttachedFileChange={setAttachedFile}
          patientLabel={patientLabel}
          onPatientLabelChange={setPatientLabel}
          vcfCount={vcfCount}
          aiEnabled={aiEnabled}
          onAiEnabledChange={setAiEnabled}
          svEnabled={svEnabled}
          onSvEnabledChange={setSvEnabled}
          pedEnabled={pedEnabled}
          onPedEnabledChange={setPedEnabled}
          thinkingEnabled={thinkingEnabled}
          onThinkingEnabledChange={setThinkingEnabled}
          onSubmit={handleSmartSubmit}
          disabled={loading}
          className="max-w-full"
          accentClassName="bg-blue-600 text-white hover:bg-blue-500 shadow-lg shadow-blue-500/25"
          placeholder="Ask a question, enter a variant (rsID/HGVS), paste long notes, or attach a VCF..."
        />

          <p className="mt-2.5 text-center text-[10px] tracking-wide text-slate-500">
            Interpret results within clinical context. Confirm with a certified counsellor.
          </p>
        </div>
      </div>
    </div>
  );
}

interface QuickActionProps {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}

function QuickAction({ icon, label, onClick }: QuickActionProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      // Against the dark gradient the previous slate-950/50 fill and slate-400
      // text were effectively invisible.
      className="flex h-8 items-center gap-2 rounded-full border border-slate-600/60 bg-slate-800/60 px-3.5 text-[11px] font-medium text-slate-200 backdrop-blur-md transition-colors duration-200 hover:border-blue-500/50 hover:bg-slate-700/70 hover:text-white"
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}
