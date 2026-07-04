export function toTitleFromSlug(value?: string | null): string {
  if (!value) return "";
  const cleaned = value.replace(/_/g, " ").trim();
  if (!cleaned) return "";
  return cleaned
    .toLowerCase()
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

