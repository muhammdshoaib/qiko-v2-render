"use client";

import { useCallback, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export type ConfirmActionConfig = {
  title: string;
  description: string;
  confirmLabel: string;
  isDestructive?: boolean;
  onConfirm: () => void;
};

type ConfirmActionDialogState = ConfirmActionConfig & {
  open: boolean;
  pending: boolean;
};

const CLOSED: ConfirmActionDialogState = {
  open: false,
  pending: false,
  title: "",
  description: "",
  confirmLabel: "Confirm",
  onConfirm: () => {},
};

/** V1 TeamAccess-style confirmation dialog for destructive actions. */
export function useConfirmActionDialog() {
  const openerRef = useRef<HTMLElement | null>(null);
  const [dialog, setDialog] = useState<ConfirmActionDialogState>(CLOSED);

  const openConfirmationDialog = useCallback((
    config: ConfirmActionConfig,
    opener?: HTMLElement | null,
  ) => {
    if (opener) openerRef.current = opener;
    setDialog({ ...config, open: true, pending: false });
  }, []);

  // EL-1023: this used to refuse to close while `pending` was still true ("if (prev.pending)
  // return prev"), to stop a user dismissing the dialog (Escape) mid-action. But most callers'
  // own onConfirm call this *itself* right after a successful mutation
  // (`onSuccess: () => closeConfirmationDialog()`), and React Query always runs onSuccess before
  // onSettled, so `pending` is still true at that exact call -- the same guard meant to protect
  // against a *user* dismissing early silently also swallowed the caller's own "we're done, close
  // now" call, leaving the dialog stuck open (data deleted, modal still showing). A couple of
  // callers (worker archive, opportunity delete) instead navigate away on success and never called
  // this while pending, so they were unaffected either way. The pending guard now lives only in
  // onOpenChange below, where it belongs: it blocks a *user-initiated* dismiss attempt, but never
  // blocks an explicit call from the caller.
  const closeConfirmationDialog = useCallback(() => {
    requestAnimationFrame(() => openerRef.current?.focus());
    setDialog(CLOSED);
  }, []);

  const setPending = useCallback((pending: boolean) => {
    setDialog((prev) => (prev.open ? { ...prev, pending } : prev));
  }, []);

  const ConfirmActionDialog = (
    <AlertDialog
      open={dialog.open}
      onOpenChange={(open: boolean) => {
        // A user-initiated dismiss via Escape is blocked while pending (Radix's AlertDialog
        // already never dismisses on backdrop/outside click by design) -- the Cancel button
        // already disables itself the same way. An explicit close from the caller
        // (closeConfirmationDialog() called directly, e.g. after a successful mutation) bypasses
        // this entirely, since it doesn't go through onOpenChange at all.
        if (!open && !dialog.pending) closeConfirmationDialog();
      }}
    >
      <AlertDialogContent className="border-white/10 bg-[#0a0f1a] text-white">
        <AlertDialogHeader>
          <AlertDialogTitle>{dialog.title}</AlertDialogTitle>
          <AlertDialogDescription className="text-slate-300">
            {dialog.description}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel
            disabled={dialog.pending}
            className="border-white/20 bg-transparent text-slate-200 hover:bg-white/10 hover:text-white"
          >
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            disabled={dialog.pending}
            className={cn(
              "inline-flex items-center justify-center gap-2 text-white disabled:pointer-events-none disabled:opacity-60",
              dialog.isDestructive !== false
                ? "bg-red-600 hover:bg-red-500"
                : "bg-emerald-600 hover:bg-emerald-500",
            )}
            onClick={(event: React.MouseEvent) => {
              event.preventDefault();
              dialog.onConfirm();
            }}
          >
            {dialog.pending ? <Loader2 className="size-3.5 shrink-0 animate-spin" /> : null}
            {dialog.pending ? `${dialog.confirmLabel.replace(/…$/, "")}…` : dialog.confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );

  return {
    openConfirmationDialog,
    closeConfirmationDialog,
    setPending,
    ConfirmActionDialog,
    // Exposed so a container that nests this dialog inside its own (e.g. a Radix Dialog around a
    // file list) can know when the confirmation is open, the same way the old per-component
    // pendingDelete state used to: Radix's Escape handling is a document-level, capture-phase
    // listener that runs before any bubble-phase handler on the confirmation itself, so the
    // container needs this to block its own onEscapeKeyDown while the confirmation is up.
    isOpen: dialog.open,
  };
}
