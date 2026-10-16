import { Badge } from "@qiko/ui";
import type { HonestyKind } from "./model";

const LABEL: Record<HonestyKind, string> = {
  live: "Live",
  connected: "Live",
  illustrative: "Illustrative",
  planned: "Pending integration",
  pending: "Pending integration",
};

const VARIANT: Record<HonestyKind, "success" | "default" | "warning" | "muted"> = {
  live: "success",
  connected: "success",
  illustrative: "warning",
  planned: "muted",
  pending: "muted",
};

export function HonestyBadge({ kind, className }: { kind: HonestyKind; className?: string }) {
  return (
    <Badge variant={VARIANT[kind]} className={className} aria-label={`Data status: ${LABEL[kind]}`}>
      {LABEL[kind]}
    </Badge>
  );
}
