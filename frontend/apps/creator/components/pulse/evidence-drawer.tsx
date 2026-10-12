import type { ReactNode } from "react";
import { Button } from "@qiko/ui";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useReferral } from "@/lib/brain/referral-store";
import { HonestyBadge } from "@/components/intelligence-layer/honesty-badge";
import { WORKERS } from "@/components/intelligence-layer/model";
import {
  BLOCKS,
  LEARNING_LABEL,
  SHEET_CLASS,
  findDetail,
  type Conversation,
  type Learning,
  type Outcome,
} from "./drilldown-data";
import { ClaudeWalkthrough } from "./claude-walkthrough";
import { OutcomeRecord } from "./outcome-record";
import { PulseChip } from "./pulse-chrome";
import { REFERRAL_ID, conversationStage } from "./referral";
import type { PulseNav } from "./route";
import { ValueSheet } from "./value-sheet";

export function EvidenceDrawer({
  nav,
  onClose,
  onNav,
  onApprove,
  onHold,
  onApproveReferral,
  onRejectReferral,
}: {
  nav: PulseNav;
  onClose: () => void;
  onNav: (next: Partial<PulseNav>) => void;
  onApprove?: () => void;
  onHold?: () => void;
  onApproveReferral?: () => void;
  onRejectReferral?: () => void;
}) {
  const referral = useReferral();
  const raw = findDetail(nav.detail);
  const item = raw?.kind === "learning" && raw.id === "l-referral"
    ? { ...raw, state: (referral.status === "approved" ? "rule" : referral.status === "rejected" ? "observed" : "proposed") as Learning["state"] }
    : raw;
  const open = Boolean(item || nav.sheet);
  const kind = nav.sheet === "claude"
    ? "Claude walkthrough"
    : nav.sheet === "value"
      ? "Knowledge value"
      : item?.kind === "conversation" ? "Conversation"
        : item?.kind === "learning" ? "Learning"
          : item?.kind === "outcome" ? "Outcome"
            : item?.kind === "source" ? "Source"
              : "Segment";
  const title = nav.sheet === "claude"
    ? "Explore the referral recommendation"
    : nav.sheet === "value"
      ? "Time saved × an agreed hourly rate"
      : item && "name" in item ? item.name : item && "title" in item ? item.title : item && "who" in item ? item.who : "Detail";
  const description = nav.sheet === "claude"
    ? "Live Claude is not connected. This is a labelled five-step walkthrough with a defined example output."
    : nav.sheet === "value"
      ? "Illustrative calculation. Uses and minutes are assumptions. Change only the hourly rate."
      : item && "from" in item ? item.from : item && "role" in item ? item.role : item && "summary" in item ? item.summary : item && "evidence" in item ? item.evidence : "";

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent className={SHEET_CLASS} aria-describedby={undefined}>
        {open && (
          <>
            <DialogHeader className="border-b border-white/10 px-6 py-5 text-left">
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-violet-400">{kind}</p>
              <div className="mt-1 flex items-start justify-between gap-3">
                <DialogTitle className="text-[19px] font-extrabold tracking-[-0.01em] text-foreground" style={{ fontFamily: "var(--font-display)" }}>
                  {title}
                </DialogTitle>
                {item && "honesty" in item && <HonestyBadge kind={item.honesty} />}
              </div>
              <DialogDescription className="text-[13.5px] leading-relaxed text-slate-400">
                {description}
              </DialogDescription>
            </DialogHeader>
            <div className="flex flex-1 flex-col gap-5 px-6 py-5">
              {nav.sheet === "claude" && onApproveReferral && onRejectReferral && (
                <ClaudeWalkthrough
                  onApprove={onApproveReferral}
                  onReject={onRejectReferral}
                  onClose={() => onNav({ sheet: null, detail: REFERRAL_ID })}
                />
              )}
              {nav.sheet === "value" && (
                <ValueSheet onClose={() => onNav({ sheet: null, detail: REFERRAL_ID })} />
              )}
              {!nav.sheet && item?.kind === "conversation" && (
                <ConversationBody
                  item={item}
                  onBlock={() => onNav({ block: item.block, worker: null, detail: null })}
                  onWorker={() => onNav({ block: item.block, worker: item.worker, pane: "conversations", detail: null })}
                  onOutcome={item.id === "c-referral" ? () => onNav({ block: "investors", worker: "intent-intelligence", pane: "outcomes", detail: REFERRAL_ID }) : undefined}
                />
              )}
              {!nav.sheet && item?.kind === "learning" && (
                <LearningBody
                  item={item}
                  onApprove={item.id === "l-referral" ? onApproveReferral : onApprove}
                  onHold={item.id === "l-referral" ? onRejectReferral : onHold}
                  onOutcome={item.id === "l-referral" ? () => onNav({ block: "investors", worker: "intent-intelligence", pane: "outcomes", detail: REFERRAL_ID }) : undefined}
                />
              )}
              {!nav.sheet && item?.kind === "outcome" && item.id === REFERRAL_ID && onApproveReferral && onRejectReferral && (
                <OutcomeRecord onNav={onNav} onApprove={onApproveReferral} onReject={onRejectReferral} />
              )}
              {!nav.sheet && item?.kind === "outcome" && item.id !== REFERRAL_ID && <OutcomeBody item={item} />}
              {!nav.sheet && item?.kind === "source" && <p className="text-[13.5px] leading-relaxed text-slate-400">{item.detail}</p>}
              {!nav.sheet && item?.kind === "segment" && (
                <div className="space-y-2 text-[13.5px] text-slate-400">
                  <p>{item.summary}</p>
                  <p className="font-medium text-foreground">{item.signal}</p>
                  {item.id === "referrals" && (
                    <Button type="button" variant="outline" onClick={() => onNav({ block: "investors", worker: "intent-intelligence", pane: "outcomes", detail: REFERRAL_ID })}>
                      Open the referral outcome
                    </Button>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ConversationBody({
  item,
  onBlock,
  onWorker,
  onOutcome,
}: {
  item: Conversation;
  onBlock: () => void;
  onWorker: () => void;
  onOutcome?: () => void;
}) {
  const referral = useReferral();
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <PulseChip>{item.channel}</PulseChip>
        <PulseChip>{item.source}</PulseChip>
        <PulseChip tone={item.id === "c-referral" ? conversationStage(referral.status).tone : item.stageTone}>
          {item.id === "c-referral" ? conversationStage(referral.status).stage : item.stage}
        </PulseChip>
      </div>
      <Section title="Conversation · highlighted text was captured">
        <div className="space-y-2">
          {item.chat.map((turn, index) => (
            <div
              key={`${turn.at}-${index}`}
              className={turn.role === "in" ? "rounded-xl bg-muted px-3 py-2.5" : "rounded-xl border border-white/10 px-3 py-2.5"}
            >
              <p className="text-[13.5px] leading-relaxed text-foreground">
                {highlight(turn.text, turn.captured)}
              </p>
              <p className="mt-1 font-mono text-[11px] text-slate-500">{turn.speaker} · {turn.at}</p>
            </div>
          ))}
        </div>
      </Section>
      <Section title="Knowledge captured">
        <div className="flex flex-wrap gap-1.5">
          {item.captured.map((fact) => (
            <PulseChip key={fact} tone="blue">{fact}</PulseChip>
          ))}
        </div>
      </Section>
      <Section title="Insight">{item.insight}</Section>
      <Section title="Next">{item.next}</Section>
      {item.handoff && (
        <div className="rounded-xl bg-muted px-3 py-3">
          <p className="text-[13px] font-semibold text-foreground">{item.handoff.label}</p>
          <p className="mt-1 text-[12.5px] text-slate-400">{item.handoff.note}</p>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={onBlock}>Back to {BLOCKS[item.block].name}</Button>
        <Button type="button" variant="ghost" onClick={onWorker}>Open {WORKERS[item.worker].name}</Button>
        {onOutcome && <Button type="button" variant="ghost" onClick={onOutcome}>Open outcome record</Button>}
      </div>
    </>
  );
}

function LearningBody({
  item,
  onApprove,
  onHold,
  onOutcome,
}: {
  item: Learning;
  onApprove?: () => void;
  onHold?: () => void;
  onOutcome?: () => void;
}) {
  const state = LEARNING_LABEL[item.state];
  return (
    <>
      <PulseChip tone={state.tone}>{state.label}</PulseChip>
      <Section title="Evidence">{item.evidence}</Section>
      {onOutcome && (
        <Button type="button" variant="outline" onClick={onOutcome}>Open the related outcome</Button>
      )}
      {item.needsApproval && onApprove && onHold && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={onApprove}>Approve review</Button>
          <Button type="button" variant="outline" onClick={onHold}>Hold</Button>
        </div>
      )}
    </>
  );
}

function OutcomeBody({ item }: { item: Outcome }) {
  return (
    <>
      <PulseChip tone={item.status === "awaiting" ? "warn" : item.status === "held" ? "" : "good"}>
        {item.status === "awaiting" ? "Awaiting you" : item.status === "held" ? "Held" : "Recorded"}
      </PulseChip>
      <Section title="Why">{item.from}</Section>
      <Section title="What was recorded">{item.summary}</Section>
      {item.sentTo.length > 0 && (
        <Section title="Landed on">
          <div className="flex flex-wrap gap-1.5">
            {item.sentTo.map((place) => <PulseChip key={place}>{place}</PulseChip>)}
          </div>
        </Section>
      )}
      <p className="font-mono text-[11px] text-slate-500">{item.when} · {WORKERS[item.worker].name}</p>
    </>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <p className="mb-2 font-mono text-[10.5px] font-medium uppercase tracking-[0.1em] text-slate-500">{title}</p>
      <div className="text-[13.5px] leading-relaxed text-slate-400">{children}</div>
    </section>
  );
}

function highlight(text: string, marks?: string[]) {
  if (!marks?.length) return text;
  const pattern = new RegExp(`(${marks.map(escapeReg).join("|")})`, "ig");
  const parts = text.split(pattern);
  return parts.map((part, index) =>
    marks.some((mark) => mark.toLowerCase() === part.toLowerCase()) ? (
      <mark key={`${part}-${index}`} className="rounded-sm bg-primary/10 px-0.5 text-primary">{part}</mark>
    ) : (
      part
    ),
  );
}

function escapeReg(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
