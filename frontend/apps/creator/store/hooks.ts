"use client";
/* Redux shim for ported pages: selectors run against an empty state (so subscription/avatar/etc.
   resolve to undefined). Typed loosely on purpose to match the original slice selectors. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function useAppSelector<T>(selector: (state: any) => T): T {
  try {
    return selector({ auth: {}, avatar: {}, worker: {}, chat: {} });
  } catch {
    return undefined as T;
  }
}

export function useAppDispatch() {
  return (_action?: unknown) => {};
}
