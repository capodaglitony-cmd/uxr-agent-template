"use client";

import { useState, useRef, useEffect } from "react";
import { fastQuery } from "@/lib/api-client";

interface Message {
  role: "user" | "assistant";
  content: string;
  model?: string;
  elapsed?: number;
  error?: boolean;
}

export function FastView({ initialPrompt }: { initialPrompt?: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState(initialPrompt ?? "");
  const [busy, setBusy] = useState(false);
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const convRef = useRef<HTMLDivElement | null>(null);

  // Auto-grow textarea up to a max.
  useEffect(() => {
    if (!taRef.current) return;
    taRef.current.style.height = "auto";
    taRef.current.style.height = Math.min(taRef.current.scrollHeight, 160) + "px";
  }, [input]);

  // Auto-scroll on new messages.
  useEffect(() => {
    convRef.current?.scrollTo({ top: convRef.current.scrollHeight });
  }, [messages]);

  // Auto-fill from prefill (e.g., wizard deny → switch to deep with the decision).
  useEffect(() => {
    if (initialPrompt) {
      setInput(initialPrompt);
      taRef.current?.focus();
    }
  }, [initialPrompt]);

  async function send() {
    const prompt = input.trim();
    if (!prompt || busy) return;
    setMessages((m) => [...m, { role: "user", content: prompt }]);
    setInput("");
    setBusy(true);
    const start = Date.now();
    try {
      const res = await fastQuery(prompt);
      const elapsed = (Date.now() - start) / 1000;
      setMessages((m) => [
        ...m,
        { role: "assistant", content: res.response, model: res.model, elapsed },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: `Error: ${e instanceof Error ? e.message : String(e)}`,
          error: true,
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div
        ref={convRef}
        className="flex-1 overflow-y-auto px-6 sm:px-8 py-6 flex flex-col gap-6"
      >
        {messages.length === 0 && (
          <div className="m-auto text-center text-textdim max-w-md">
            <h2 className="text-base font-normal text-textmuted mb-2">
              Fast mode
            </h2>
            <p className="text-[13px] leading-relaxed">
              Single Anthropic call. ~3-5s. Press Enter to send.
            </p>
          </div>
        )}
        {messages.map((m, i) => (
          <Bubble key={i} message={m} />
        ))}
        {busy && (
          <div className="text-[11px] font-mono text-warn-text flex items-center gap-1.5 self-start">
            <span className="w-1.5 h-1.5 rounded-full bg-warn-text animate-pulse-dot" />
            Synthesizing...
          </div>
        )}
      </div>
      <div className="border-t border-border1 bg-surface px-6 py-4">
        <div className="flex gap-2.5 items-end">
          <textarea
            ref={taRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Ask a question about the corpus..."
            rows={1}
            disabled={busy}
            className="flex-1 bg-bg border border-border2 rounded-md px-3.5 py-2.5 text-textmain font-sans text-[14px] leading-snug outline-none focus:border-accent transition resize-none min-h-[44px] max-h-40 placeholder:text-textdim disabled:opacity-50"
          />
          <button
            type="button"
            onClick={send}
            disabled={busy || !input.trim()}
            className="px-5 py-2.5 bg-accent border border-accent-bright rounded-md text-textmain font-mono text-[12px] cursor-pointer hover:bg-accent-bright transition h-[44px] disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
          >
            send ↩
          </button>
        </div>
      </div>
    </div>
  );
}

function Bubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  return (
    <div
      className={[
        "flex flex-col gap-1.5 max-w-3xl",
        isUser ? "self-end items-end" : "self-start items-start",
      ].join(" ")}
    >
      <div className="text-[10px] font-mono uppercase tracking-[1.5px] text-textdim">
        {isUser ? "YOU" : "CORPUS"}
        {message.model && (
          <span className="ml-2 normal-case tracking-normal">
            · {message.model}
            {message.elapsed != null ? ` · ${message.elapsed.toFixed(1)}s` : ""}
          </span>
        )}
      </div>
      <div
        className={[
          "px-4 py-3 leading-relaxed text-[14px] rounded-md whitespace-pre-wrap",
          isUser
            ? "bg-accent-glow border border-accent rounded-br-sm"
            : message.error
            ? "bg-err border border-err-text text-err-text font-mono text-[12px]"
            : "bg-surface border border-border1 rounded-bl-sm min-w-[200px]",
        ].join(" ")}
      >
        {message.content}
      </div>
    </div>
  );
}
