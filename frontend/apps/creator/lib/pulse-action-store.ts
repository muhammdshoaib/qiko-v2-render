/** Shared human action backlog for Pulse + Knowledge Overview/Analytics. */

export type SharedActionStatus = "todo" | "in_progress" | "done";

export type SharedPulseAction = {
  id: string;
  title: string;
  insightTitle: string;
  source: string;
  status: SharedActionStatus;
  createdAt: string;
};

const KEY = "qiko.pulse.action-list.v1";

function read(): SharedPulseAction[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as SharedPulseAction[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function write(items: SharedPulseAction[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, JSON.stringify(items));
  window.dispatchEvent(new CustomEvent("qiko-pulse-actions"));
}

export function listSharedPulseActions() {
  return read();
}

export function addSharedPulseAction(input: {
  title: string;
  insightTitle: string;
  source: string;
}) {
  const next: SharedPulseAction = {
    id: `shared-${Date.now()}`,
    title: input.title,
    insightTitle: input.insightTitle,
    source: input.source,
    status: "todo",
    createdAt: new Date().toISOString(),
  };
  write([next, ...read()]);
  return next;
}

export function setSharedPulseActionStatus(id: string, status: SharedActionStatus) {
  write(read().map((item) => (item.id === id ? { ...item, status } : item)));
}

export function subscribeSharedPulseActions(cb: () => void) {
  if (typeof window === "undefined") return () => undefined;
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY) cb();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener("qiko-pulse-actions", cb);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener("qiko-pulse-actions", cb);
  };
}
