"use client";

import Markdown from "react-markdown";
import { cn } from "@qiko/ui";

/** Renders an assistant/user chat message. Assistant text comes back from the LLM as markdown
 * (headings, bold, lists, ...) -- rendering it as plain text left the raw #/** syntax visible to
 * end users, so this renders it properly instead. User text is shown as-is (it's not markdown,
 * and echoing raw markdown syntax back at someone who typed "5 * 3" would be wrong anyway). */
export function ChatBubble({ role, text, variant = "default" }: {
  role: string; text: string; variant?: "default" | "gradient";
}) {
  const isUser = role === "user";
  return (
    <div className={cn("max-w-[85%] rounded-2xl px-3.5 py-2 text-sm", isUser ? "rounded-br-sm" : "rounded-bl-sm",
      isUser
        ? variant === "gradient" ? "bg-gradient-to-r from-primary to-cyan-400 text-white" : "bg-primary text-primary-foreground"
        : "bg-muted text-foreground")}>
      {isUser ? (
        <span className="whitespace-pre-wrap">{text}</span>
      ) : (
        <Markdown
          components={{
            p: ({ children }) => <p className="mb-2 leading-relaxed last:mb-0">{children}</p>,
            ul: ({ children }) => <ul className="mb-2 ml-4 list-disc space-y-0.5 last:mb-0">{children}</ul>,
            ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal space-y-0.5 last:mb-0">{children}</ol>,
            li: ({ children }) => <li className="leading-relaxed">{children}</li>,
            h1: ({ children }) => <p className="mb-1 mt-1 text-[0.95em] font-bold first:mt-0">{children}</p>,
            h2: ({ children }) => <p className="mb-1 mt-1 text-[0.95em] font-bold first:mt-0">{children}</p>,
            h3: ({ children }) => <p className="mb-1 mt-1 text-[0.9em] font-semibold first:mt-0">{children}</p>,
            strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
            a: ({ children, href }) => (
              <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:opacity-80">
                {children}
              </a>
            ),
            code: ({ children }) => (
              <code className="rounded bg-black/10 px-1 py-0.5 font-mono text-[0.85em] dark:bg-white/10">{children}</code>
            ),
            hr: () => <hr className="my-2 border-current/10" />,
          }}
        >
          {text}
        </Markdown>
      )}
    </div>
  );
}

/** Three staggered bouncing dots -- shown while a worker is generating a reply. Replaces a
 * static "Thinking..." string, which gave no sense that anything was actually happening. */
export function TypingIndicator({ variant = "default" }: { variant?: "default" | "gradient" }) {
  return (
    <div className={cn("inline-flex items-center gap-1 rounded-2xl rounded-bl-sm px-4 py-3",
      variant === "gradient" ? "bg-white/[0.06]" : "bg-muted")}>
      {[0, 1, 2].map((i) => (
        <span key={i} className="size-1.5 animate-bounce rounded-full bg-current opacity-60"
          style={{ animationDelay: `${i * 0.15}s`, animationDuration: "0.9s" }} />
      ))}
    </div>
  );
}
