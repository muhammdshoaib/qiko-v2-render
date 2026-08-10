"use client";

/**
 * The audit trail, narrowed to one thing, embedded where an operator already is.
 *
 * The global /audit page is the surface an auditor uses. This is the one operators actually use, because
 * they arrive from an account rather than from a search box: the question is almost never "what happened
 * on the platform" and almost always "what happened to THIS tenant before I touch it".
 *
 * Three things it has to get right that the global page does not.
 *
 * It must degrade rather than break. Most admins reading a customer record do not hold view_audit, and a
 * 403 here must not take down the dialog it sits inside.
 *
 * It must be honest about what it does not cover. Worker availability changes still live in the older
 * agent_state_audit table and are not in this stream, so a reader seeing an empty panel must not
 * conclude nothing happened.
 *
 * It must lead somewhere. Five entries answer "is anything odd here"; the link answers everything else.
 */
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Alert, Badge, Skeleton } from "@qiko/ui";
import { auditEvents, type AuditEvent } from "@/lib/api";
import { ACTOR_LABELS, headline, relativeWhen } from "@/lib/audit-format";

type Scope =
  | { tenantId: string; targetId?: never }
  | { targetId: string; tenantId?: never };

export function RecentActivity({
  scope, limit = 5, note,
}: {
  scope: Scope;
  limit?: number;
  /** Named gap in coverage, shown when there is one. See the module docstring. */
  note?: string;
}) {
  const filter = scope.tenantId ? { tenant_id: scope.tenantId } : { target_id: scope.targetId };
  const activity = useQuery({
    queryKey: ["recent-activity", filter, limit],
    // 400 days rather than the default 7: on a rarely-touched account the last thing that happened is
    // the interesting thing, however long ago it was, and an empty panel because the window was short
    // is indistinguishable from an empty panel because nothing happened.
    queryFn: () => auditEvents({ ...filter, days: 400, limit }),
    // A reader without view_audit gets a 403. That is expected, not an error worth retrying or
    // reporting: this panel is supplementary to whatever it is embedded in.
    retry: false,
  });

  const href = scope.tenantId
    ? `/audit?tenant=${encodeURIComponent(scope.tenantId)}&days=400`
    : `/audit?target=${encodeURIComponent(scope.targetId!)}&days=400`;

  return (
    <section aria-labelledby="recent-activity-heading" className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h3 id="recent-activity-heading" className="font-semibold">Recent activity</h3>
        {activity.isSuccess && (
          <Link href={href} className="text-sm underline decoration-dotted">
            Open in audit log
          </Link>
        )}
      </div>

      {activity.isLoading && (
        <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
      )}

      {activity.isError && (
        // Deliberately not an error tone. Being refused is a normal state here, and a red box inside a
        // customer record reads as something being broken.
        <p className="text-sm text-muted-foreground">
          Activity history needs the Read the audit log capability.
        </p>
      )}

      {activity.isSuccess && activity.data.items.length === 0 && (
        <p className="text-sm text-muted-foreground">No recorded activity.</p>
      )}

      {activity.isSuccess && activity.data.items.length > 0 && (
        <ul className="space-y-2">
          {activity.data.items.map((event: AuditEvent) => (
            <li key={event.event_id} className="rounded-lg border border-border p-3 text-sm">
              <p className="font-medium">{headline(event)}</p>
              <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                <span title={event.occurred_at}>{relativeWhen(event.occurred_at)}</span>
                <span aria-hidden="true">&middot;</span>
                <Badge variant="muted">{ACTOR_LABELS[event.actor_type] ?? event.actor_type}</Badge>
                {event.outcome !== "success" && (
                  <Badge variant={event.outcome === "denied" ? "warning" : "destructive"}>
                    {event.outcome === "denied" ? "Denied" : "Failed"}
                  </Badge>
                )}
              </p>
              {event.reason && <p className="mt-1 text-xs italic">{event.reason}</p>}
            </li>
          ))}
        </ul>
      )}

      {/* Shown even when the list is populated: the gap does not disappear because something else was
          recorded. */}
      {note && activity.isSuccess && (
        <Alert tone="info" className="text-xs">{note}</Alert>
      )}
    </section>
  );
}
