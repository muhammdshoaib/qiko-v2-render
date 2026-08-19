// Route prefixes rendered inside <AppShell> (components/app-shell.tsx). AppShell owns a
// persistent sidebar (with a full-width Logout button pinned to its bottom) and, on the Studio
// cockpit routes, a chat panel that also pins its composer to a screen edge. The global floating
// cookie-settings button has twice been repositioned to dodge one of these and landed on the
// other (fix/qiko-1005-cookie-logout moved it off Logout onto the chat send button, EL-1001).
// AppShell'd routes keep an in-app entry point instead (Settings > Privacy choices), so the
// floating button only needs to render on shell-less public/marketing/auth pages.
export const APP_SHELL_ROUTE_PREFIXES = ["/workers", "/studio", "/settings", "/dashboard", "/chat", "/billing"] as const;

export function isAppShellRoute(pathname: string): boolean {
  return APP_SHELL_ROUTE_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}
