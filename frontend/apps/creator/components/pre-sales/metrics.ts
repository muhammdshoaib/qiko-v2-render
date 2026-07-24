export const AI_DRAFTING_DESCRIPTION =
  "AI drafting progress is total completed drafts divided by total draftable items across active bids. It does not measure answer quality, confidence, grounding, or KB gaps.";

type DraftingPack = {
  gen_status?: {
    drafts?: {
      done?: number | null;
      total?: number | null;
    } | null;
  } | null;
};

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
