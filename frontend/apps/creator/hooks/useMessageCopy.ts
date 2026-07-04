"use client";
import { useRef, useState } from "react";
import { toast } from "sonner";

type MessageId = number | string;

export function useMessageCopy(timeoutMs = 1500) {
  const [copiedMessageId, setCopiedMessageId] = useState<MessageId | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearCopyState = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    setCopiedMessageId(null);
  };

  const copyMessage = async (messageId: MessageId, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessageId(messageId);
      toast.success("Message copied");

      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }

      timeoutRef.current = setTimeout(() => {
        setCopiedMessageId(null);
        timeoutRef.current = null;
      }, timeoutMs);
    } catch {
      toast.error("Unable to copy message");
    }
  };

  return {
    copiedMessageId,
    copyMessage,
    clearCopyState,
  };
}
