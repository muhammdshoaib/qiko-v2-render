export const AI_DRAFTING_DESCRIPTION =
  "AI drafting progress is total completed drafts divided by total draftable items across active bids. It does not measure answer quality, confidence, grounding, or KB gaps.";

type DeadlinePack = {
  deadline?: string | null;
};

type KnowledgeDocument = {
  chunks?: number | null;
};

type DraftingPack = {
  gen_status?: {
    drafts?: {
      done?: number | null;
      total?: number | null;
    } | null;
  } | null;
};

function deadlineTimestamp(value: string): number {
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!dateOnly) return new Date(value).getTime();

  const year = Number(dateOnly[1]);
  const month = Number(dateOnly[2]);
  const day = Number(dateOnly[3]);
  const deadline = new Date(year, month - 1, day, 23, 59, 59, 999);
  if (
    deadline.getFullYear() !== year
    || deadline.getMonth() !== month - 1
    || deadline.getDate() !== day
  ) return Number.NaN;
  return deadline.getTime();
}

export function nextBidDeadline(
  packs: readonly DeadlinePack[],
  now: Date | number,
): string | null {
  const nowTime = now instanceof Date ? now.getTime() : now;
  if (!Number.isFinite(nowTime)) return null;

  let nearestDeadline: string | null = null;
  let nearestTime = Number.POSITIVE_INFINITY;
  for (const pack of packs) {
    if (!pack.deadline) continue;
    const deadlineTime = deadlineTimestamp(pack.deadline);
    if (
      !Number.isFinite(deadlineTime)
      || deadlineTime <= nowTime
      || deadlineTime >= nearestTime
    ) continue;
    nearestDeadline = pack.deadline;
    nearestTime = deadlineTime;
  }
  return nearestDeadline;
}

export function knowledgeChunkCount(documents: readonly KnowledgeDocument[]): number {
  return documents.reduce((total, document) => {
    const chunks = document.chunks;
    return typeof chunks === "number" && Number.isFinite(chunks) && chunks > 0
      ? total + chunks
      : total;
  }, 0);
}

export function aiDraftingPercent(packs: readonly DraftingPack[]): number | null {
  let completed = 0;
  let draftable = 0;

  for (const pack of packs) {
    const drafts = pack.gen_status?.drafts;
    const total = drafts?.total;
    if (typeof total !== "number" || !Number.isFinite(total) || total <= 0) continue;
    const rawDone = drafts?.done;
    const done = typeof rawDone === "number" && Number.isFinite(rawDone) ? rawDone : 0;
    completed += Math.min(total, Math.max(0, done));
    draftable += total;
  }

  return draftable > 0 ? Math.round((completed / draftable) * 100) : null;
}
