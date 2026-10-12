const LOCAL_API = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?\/api\/v1\/?$/i;

/** FastAPI origin used by Creator /health and the /api proxy when API_UPSTREAM is unset. */
export function resolveApiOrigin(): string {
  const upstream = process.env.API_UPSTREAM?.replace(/\/$/, "");
  if (upstream) return upstream;

  const publicBase = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "";
  if (/^https?:\/\//i.test(publicBase) && !LOCAL_API.test(publicBase)) {
    return publicBase.replace(/\/api\/v1$/, "");
  }

  // Windows Node often resolves `localhost` to ::1 while FastAPI is on 127.0.0.1.
  return "http://127.0.0.1:8000";
}

/** Browser calls stay same-origin so local login is not blocked by CORS. */
export function clientApiBase(): string {
  const configured = (process.env.NEXT_PUBLIC_API_BASE ?? "/api/v1").replace(/\/$/, "");
  if (!configured || LOCAL_API.test(configured)) return "/api/v1";
  return configured;
}
