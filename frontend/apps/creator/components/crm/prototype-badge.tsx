import { Badge } from "@qiko/ui";

export function PrototypeBadge({
  label = "Prototype",
  tone = "warning",
  className,
}: {
  label?: string;
  tone?: "warning" | "muted" | "default";
  className?: string;
}) {
  return (
    <Badge variant={tone} className={className} aria-label={`Data status: ${label}`}>
      {label}
    </Badge>
  );
}
