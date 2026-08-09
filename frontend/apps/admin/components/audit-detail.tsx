"use client";

/**
 * The detail drawer for one audit event.
 *
 * Ordered by what a reader actually wants, which is not the order the data is stored in: the sentence
 * first and largest, then the operator's reason, then the change table, then context, and the raw JSON
 * last behind a disclosure because auditors ask for it and operators never look at it.
 *
 * The request correlation link is the part that has no equivalent in the tools this was modelled on. A
 * multi-step admin action produces several rows; being able to see them as one operation is the thing
 * an operator reaches for during an incident.
 */
import { useRef } from "react";
import { Badge, Button, Dialog } from "@qiko/ui";
import type { AuditEvent } from "@/lib/api";
import {
  ACTOR_LABELS, CATEGORY_LABELS, changeRows, formatWhen, formatWhenUtc, headline,
} from "@/lib/audit-format";

export function AuditDetail({ event, onClose, onFilter }: {
  event: AuditEvent | null;
  onClose: () => void;
  onFilter: (key: string, value: string) => void;
}) {
  const opener = useRef<HTMLElement | null>(null);
  if (typeof document !== "undefined" && event && !opener.current) {
    opener.current = document.activeElement as HTMLElement;
  }
  if (!event) opener.current = null;

  const changes = event ? changeRows(event) : [];
  const metadata = Object.entries(event?.metadata ?? {});

  return (
    <Dialog open={Boolean(event)} onClose={onClose} opener={opener.current}
      labelledBy="audit-detail-title" className="max-w-2xl">
      {event && (
        <div className="space-y-5">
          <div>
            {/* The sentence the server rendered at write time. Fixed at the moment it happened, so a
                later rename cannot rewrite history. */}
            <h2 id="audit-detail-title" className="text-lg font-semibold leading-snug">
              {headline(event)}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {formatWhen(event.occurred_at)}
              <span className="mx-1">&middot;</span>
              {/* Both zones, labelled. Every auditor conversation is in UTC and every operator thinks
                  in local time. */}
              {formatWhenUtc(event.occurred_at)}
            </p>
          </div>

          {/* Above the diff on purpose: operators care about why more than about which field moved. */}
          {event.reason && (
            <blockquote className="border-l-2 border-border pl-3 text-sm italic">
              {event.reason}
            </blockquote>
          )}

          {changes.length > 0 && (
            <div>
              <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                What changed
              </h3>
              <table className="w-full text-sm">
                <caption className="sr-only">Fields changed by this event</caption>
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th scope="col" className="py-1 pr-3 text-left font-medium">Field</th>
                    <th scope="col" className="py-1 pr-3 text-left font-medium">From</th>
                    <th scope="col" className="py-1 text-left font-medium">To</th>
                  </tr>
                </thead>
                <tbody>
                  {changes.map((row) => (
                    <tr key={row.field} className="border-b border-border/60 last:border-0">
                      <th scope="row" className="py-2 pr-3 text-left font-normal">{row.label}</th>
                      {/* Muted rather than red, and green for the new value. Colour is a hint here,
                          not the information: the column headers already say which side is which. */}
                      <td className="py-2 pr-3 text-muted-foreground line-through decoration-1">
                        {row.from}
                      </td>
                      <td className="py-2 font-medium text-success">{row.to}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Context
            </h3>
            <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1.5 text-sm">
              <dt className="text-muted-foreground">Actor</dt>
              <dd>
                {event.actor_label || event.actor_id || "System"}
                <Badge variant="muted" className="ml-2">
                  {ACTOR_LABELS[event.actor_type] ?? event.actor_type}
                </Badge>
              </dd>

              {event.on_behalf_of && (
                <>
                  <dt className="text-muted-foreground">On behalf of</dt>
                  {/* Support access. The human who initiated is always the actor; this is who they were
                      acting for, and conflating the two is what makes an audit useless in exactly the
                      situation it exists for. */}
                  <dd>{event.on_behalf_of}</dd>
                </>
              )}

              <dt className="text-muted-foreground">Target</dt>
              <dd>
                {event.target_label || event.target_id || "-"}
                <span className="ml-2 text-xs text-muted-foreground">{event.target_type}</span>
              </dd>

              <dt className="text-muted-foreground">Tenant</dt>
              <dd>
                {event.tenant_id
                  ? <button type="button" className="underline decoration-dotted"
                      onClick={() => { onFilter("tenant", event.tenant_id!); onClose(); }}>
                      {event.tenant_id}
                    </button>
                  : "Platform-wide"}
              </dd>

              <dt className="text-muted-foreground">Category</dt>
              <dd>{CATEGORY_LABELS[event.category] ?? event.category}
                <span className="ml-2 text-xs text-muted-foreground">{event.action}</span></dd>

              <dt className="text-muted-foreground">Outcome</dt>
              <dd>{event.outcome}</dd>

              {event.source_ip && (<><dt className="text-muted-foreground">Address</dt>
                <dd className="tabular-nums">{event.source_ip}</dd></>)}

              {event.route && (<><dt className="text-muted-foreground">Route</dt>
                <dd className="break-all text-xs">{event.route}</dd></>)}

              <dt className="text-muted-foreground">Environment</dt>
              <dd>{event.environment} <span className="text-xs text-muted-foreground">({event.service})</span></dd>
            </dl>
          </div>

          {event.request_id && (
            <div className="rounded-lg border border-border bg-muted/30 p-3">
              <p className="text-sm">
                This event was part of one request.{" "}
                <button type="button" className="underline"
                  onClick={() => { onFilter("request", event.request_id!); onClose(); }}>
                  Show everything from that request
                </button>
              </p>
              <p className="mt-1 font-mono text-xs text-muted-foreground">{event.request_id}</p>
            </div>
          )}

          {metadata.length > 0 && (
            <details>
              <summary className="cursor-pointer text-sm text-muted-foreground">
                Additional detail
              </summary>
              <dl className="mt-2 grid grid-cols-[10rem_1fr] gap-x-3 gap-y-1 text-sm">
                {metadata.map(([key, value]) => (
                  <div key={key} className="col-span-2 grid grid-cols-subgrid">
                    <dt className="text-muted-foreground">{key.replace(/_/g, " ")}</dt>
                    <dd className="break-all">
                      {typeof value === "boolean" ? (value ? "Yes" : "No")
                        : value === null ? "Unknown"
                          : typeof value === "object" ? JSON.stringify(value) : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          )}

          {/* Last, and collapsed. Auditors ask for it; operators ignore it. */}
          <details>
            <summary className="cursor-pointer text-sm text-muted-foreground">Raw event</summary>
            <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-muted/40 p-3 text-xs">
              {JSON.stringify(event, null, 2)}
            </pre>
          </details>

          <div className="flex justify-end">
            <Button variant="outline" onClick={onClose}>Close</Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
