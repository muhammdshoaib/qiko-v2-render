export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const upstream = process.env.API_UPSTREAM?.replace(/\/$/, "");
  if (!upstream) return;

  const ping = () => fetch(`${upstream}/health`, { cache: "no-store" }).catch(() => undefined);
  void ping();
  setInterval(ping, 4 * 60 * 1000);
}
