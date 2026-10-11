import { Badge } from "@qiko/ui";
import type { HonestyKind } from "./model";

const LABEL: Record<HonestyKind, string> = {
  live: "Live",
  connected: "Connected",
  illustrative: "Illustrative",
  planned: "Planned",
};

const VARIANT: Record<HonestyKind, "success" | "default" | "warning" | "muted"> = {
  live: "success",
  connected: "default",
  illustrative: "warning",
  planned: "muted",
};

export function HonestyBadge({ kind, className }: { kind: HonestyKind; className?: string }) {
  return (
    <Badge variant={VARIANT[kind]} className={className} aria-label={`Data status: ${LABEL[kind]}`}>
      {LABEL[kind]}
    </Badge>
  );
}
