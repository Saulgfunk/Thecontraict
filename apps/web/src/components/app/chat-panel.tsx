"use client";

import { MessageSquarePlus, Send, Trash2 } from "lucide-react";
import { Fragment, useEffect, useRef, useState } from "react";

import { Button, ErrorText, Loading, Select } from "@/components/ui";
import {
  useChatThread,
  useChatThreads,
  useCreateChatThread,
  useDeleteChatThread,
  useSendChatMessage,
  type Schemas,
} from "@/lib/api";
import { cn, errorMessage } from "@/lib/utils";

type Message = Schemas["MessageOut"];
export type ChatCitation = Schemas["Citation"];

const SUGGESTIONS_CONTRACT = [
  "When is the last day to give notice of non-renewal?",
  "Can we terminate early, and on what conditions?",
  "What are the payment terms and any price increases?",
  "Is there a liability cap?",
];
const SUGGESTIONS_WORKSPACE = [
  "Which contracts renew automatically in the next 6 months?",
  "Which contracts allow termination for convenience?",
  "Compare the payment terms across these contracts.",
  "Which contracts have notice deadlines this quarter?",
];

/** Renders **bold** and keeps line breaks; enough for typical answers. */
function RichText({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("**") && p.endsWith("**") ? (
          <strong key={i}>{p.slice(2, -2)}</strong>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  );
}

function AssistantMessage({
  message,
  onCitation,
}: {
  message: Message;
  onCitation: (c: ChatCitation) => void;
}) {
  const sources: ChatCitation[] = [];
  const indexOf = (c: ChatCitation) => {
    const key = `${c.contract_id}|${c.clause_refs.join(",")}`;
    let i = sources.findIndex((s) => `${s.contract_id}|${s.clause_refs.join(",")}` === key);
    if (i < 0) {
      sources.push(c);
      i = sources.length - 1;
    }
    return i + 1;
  };
  const rendered = (message.blocks ?? []).map((b, i) => (
    <Fragment key={i}>
      <RichText text={b.text} />
      {(b.citations ?? []).map((c) => {
        const n = indexOf(c);
        return (
          <button
            key={`${i}-${n}`}
            type="button"
            title={c.cited_text}
            onClick={() => onCitation(c)}
            className="bg-primary/10 text-primary hover:bg-primary/20 mx-0.5 inline-flex h-4 min-w-4 -translate-y-1 items-center justify-center rounded px-1 align-baseline text-[10px] font-semibold"
          >
            {n}
          </button>
        );
      })}
    </Fragment>
  ));
  return (
    <div className="min-w-0 space-y-2">
      <div className="text-sm leading-relaxed break-words whitespace-pre-wrap">{rendered}</div>
      {message.error && <ErrorText>{message.error}</ErrorText>}
      {sources.length > 0 && (
        <ol className="border-border text-muted space-y-1 border-t pt-2 text-xs">
          {sources.map((s, i) => (
            <li key={i}>
              <button
                type="button"
                className="hover:text-foreground block w-full min-w-0 text-left"
                onClick={() => onCitation(s)}
              >
                <span className="text-primary font-semibold">{i + 1}.</span> {s.contract_title}
                {s.clause_refs.length > 0 && ` · ${s.clause_refs.join(", ")}`}
                <span className="block truncate italic">“{s.cited_text}”</span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function ChatPanel({
  orgId,
  workspaceId,
  contractId,
  onCitation,
  className,
}: {
  orgId: string;
  workspaceId: string;
  contractId?: string;
  onCitation: (c: ChatCitation) => void;
  className?: string;
}) {
  const threads = useChatThreads(orgId, {
    workspace_id: workspaceId,
    ...(contractId ? { contract_id: contractId } : {}),
  });
  // Workspace chat lists only workspace-wide threads.
  const list = (threads.data ?? []).filter((t) => (contractId ? true : !t.contract_id));
  const [selected, setSelected] = useState<string | null | undefined>(undefined);
  const activeId = selected === undefined ? (list[0]?.id ?? null) : selected;
  const thread = useChatThread(orgId, activeId);
  const createThread = useCreateChatThread(orgId);
  const deleteThread = useDeleteChatThread(orgId);
  const send = useSendChatMessage(orgId);

  const [input, setInput] = useState("");
  const [pending, setPending] = useState<{ question: string; answer: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [thread.data?.messages.length, pending?.answer]);

  const ask = async (question: string) => {
    question = question.trim();
    if (!question || pending) return;
    setError(null);
    setInput("");
    let id = activeId;
    if (!id) {
      try {
        const created = (await createThread.mutateAsync({
          workspace_id: workspaceId,
          contract_id: contractId ?? null,
        })) as Schemas["ThreadOut"];
        id = created.id;
        setSelected(id);
      } catch (e) {
        setError(errorMessage(e));
        return;
      }
    }
    setPending({ question, answer: "" });
    await send(id, question, (event) => {
      if (event.type === "delta") {
        setPending((p) => (p ? { ...p, answer: p.answer + event.text } : p));
      } else if (event.type === "error") {
        setError(event.detail);
      }
    });
    await thread.refetch();
    setPending(null);
  };

  const messages = thread.data?.messages ?? [];
  const suggestions = contractId ? SUGGESTIONS_CONTRACT : SUGGESTIONS_WORKSPACE;

  return (
    <div className={cn("flex min-h-0 min-w-0 flex-col", className)}>
      <div className="mb-3 flex items-center gap-2">
        <Select
          aria-label="Conversation"
          className="h-8 min-w-0 flex-1 text-xs"
          value={activeId ?? ""}
          onChange={(e) => setSelected(e.target.value || null)}
        >
          <option value="">New conversation</option>
          {list.map((t) => (
            <option key={t.id} value={t.id}>
              {t.title}
            </option>
          ))}
        </Select>
        <Button
          variant="secondary"
          className="h-8 px-2"
          title="New conversation"
          onClick={() => setSelected(null)}
        >
          <MessageSquarePlus className="size-4" />
        </Button>
        {activeId && (
          <Button
            variant="ghost"
            className="text-muted h-8 px-2"
            title="Delete conversation"
            onClick={() =>
              deleteThread.mutate(activeId, { onSuccess: () => setSelected(undefined) })
            }
          >
            <Trash2 className="size-4" />
          </Button>
        )}
      </div>

      <div className="border-border bg-background min-h-0 flex-1 space-y-4 overflow-y-auto rounded-md border p-3">
        {activeId && thread.isPending && <Loading />}
        {!messages.length && !pending && !(activeId && thread.isPending) && (
          <div className="space-y-2">
            <p className="text-muted text-sm">
              Ask anything about {contractId ? "this contract" : "the contracts in this workspace"}.
              Answers cite the clauses they rely on.
            </p>
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => void ask(s)}
                className="border-border bg-surface hover:border-primary/50 block w-full rounded-md border px-3 py-2 text-left text-sm"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="bg-primary/10 ml-8 rounded-lg px-3 py-2 text-sm">
              {m.blocks.map((b) => b.text).join("")}
            </div>
          ) : (
            <AssistantMessage key={m.id} message={m} onCitation={onCitation} />
          ),
        )}
        {pending && (
          <>
            <div className="bg-primary/10 ml-8 rounded-lg px-3 py-2 text-sm">
              {pending.question}
            </div>
            <div className="text-sm leading-relaxed whitespace-pre-wrap">
              {pending.answer || <span className="text-muted">Reading the contracts…</span>}
            </div>
          </>
        )}
        <div ref={bottom} />
      </div>

      <ErrorText>{error}</ErrorText>
      <form
        className="mt-3 flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(input);
        }}
      >
        <textarea
          aria-label="Your question"
          className="border-border bg-surface focus:ring-primary/40 max-h-40 min-h-9 flex-1 resize-y rounded-md border px-3 py-2 text-sm outline-none focus:ring-2"
          rows={2}
          placeholder="Ask a question…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask(input);
            }
          }}
        />
        <Button type="submit" disabled={!input.trim() || !!pending} aria-label="Send">
          <Send className="size-4" />
        </Button>
      </form>
      <p className="text-muted mt-1 text-xs">
        AI answers can be wrong. Check the cited clauses before relying on them.
      </p>
    </div>
  );
}
