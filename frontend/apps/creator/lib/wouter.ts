"use client";
// wouter-compatible shim backed by next/navigation, so ported pages keep `useLocation`.
import { useRouter, usePathname, useParams as useNextParams } from "next/navigation";

export function useLocation(): [string, (to: string) => void] {
  const router = useRouter();
  const pathname = usePathname();
  return [pathname, (to: string) => router.push(to)];
}

export function useParams<T extends Record<string, string> = Record<string, string>>(): T {
  return useNextParams() as T;
}
