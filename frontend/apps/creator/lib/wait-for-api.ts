const READY_TIMEOUT_MS = 90_000;
const POLL_MS = 3_000;

export async function waitForApi(timeoutMs = READY_TIMEOUT_MS): Promise<boolean> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch("/health", { cache: "no-store" });
      const body = (await res.json()) as { status?: string; service?: string };
      if (res.ok && body.status === "ok" && body.service === "qiko-core") return true;
    } catch {
      // API is still waking.
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_MS));
  }
  return false;
}
