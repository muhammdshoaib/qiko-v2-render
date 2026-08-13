export const BEHAVIOR_MAX_ENTRIES = 50;
export const BEHAVIOR_MAX_TITLE = 255;
export const BEHAVIOR_MAX_CONTENT = 4000;

export type BehaviorEntry = {
  id: string;
  title: string;
  content: string;
};

type BehaviorEntryInput = {
  id?: unknown;
  title?: unknown;
  content?: unknown;
  description?: unknown;
};

function generatedBehaviorId(title: string, content: string, index: number): string {
  const value = `${index}\u0000${title}\u0000${content}`;
  let hash = 2166136261;

  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }

  return `behavior-${(hash >>> 0).toString(36)}`;
}

export function normalizeBehaviorEntries(value: unknown): BehaviorEntry[] {
  const values = Array.isArray(value) ? value : value == null ? [] : [value];
  const usedIds = new Set<string>();

  return values.flatMap((raw, index) => {
    let id = "";
    let title = "";
    let content = "";

    if (typeof raw === "string") {
      title = raw;
    } else if (typeof raw === "object" && raw !== null) {
      const entry = raw as BehaviorEntryInput;
      id = typeof entry.id === "string" ? entry.id.trim() : "";
      title = typeof entry.title === "string" ? entry.title : "";
      content = typeof entry.content === "string"
        ? entry.content
        : typeof entry.description === "string"
          ? entry.description
          : "";
    } else {
      return [];
    }

    const baseId = id || generatedBehaviorId(title, content, index);
    let uniqueId = baseId;
    let suffix = 2;
    while (usedIds.has(uniqueId)) {
      uniqueId = `${baseId}-${suffix}`;
      suffix += 1;
    }
    usedIds.add(uniqueId);

    return [{ id: uniqueId, title, content }];
  });
}

export function serializeBehaviorEntries(entries: readonly BehaviorEntry[]): BehaviorEntry[] {
  return entries.map(({ id, title, content }) => ({ id, title, content }));
}

export function validateBehaviorEntry(entry: Pick<BehaviorEntry, "title" | "content">): string | null {
  const title = entry.title.trim();
  const content = entry.content.trim();

  if (!title) return "Title is required.";
  if (title.length > BEHAVIOR_MAX_TITLE) return `Title must be ${BEHAVIOR_MAX_TITLE} characters or fewer.`;
  if (!content) return "Content is required.";
  if (content.length > BEHAVIOR_MAX_CONTENT) return `Content must be ${BEHAVIOR_MAX_CONTENT} characters or fewer.`;
  return null;
}

export function upsertBehaviorEntry(
  entries: readonly BehaviorEntry[],
  entry: BehaviorEntry,
): BehaviorEntry[] {
  const index = entries.findIndex((current) => current.id === entry.id);
  if (index === -1) return [...entries, { ...entry }];
  return entries.map((current, currentIndex) => currentIndex === index ? { ...entry } : current);
}

export function removeBehaviorEntry(entries: readonly BehaviorEntry[], entryId: string): BehaviorEntry[] {
  return entries.filter((entry) => entry.id !== entryId);
}
