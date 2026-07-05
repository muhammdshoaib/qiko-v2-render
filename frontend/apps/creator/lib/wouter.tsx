"use client";
// wouter-compatible shim backed by next/navigation, so ported pages keep `useLocation`/`Link`.
import { useRouter, usePathname, useParams as useNextParams } from "next/navigation";
import NextLink from "next/link";
import type { ComponentProps } from "react";

export function Link({ href, children, ...rest }: { href: string } & Omit<ComponentProps<typeof NextLink>, "href">) {
  return (
    <NextLink href={href} {...rest}>
      {children}
    </NextLink>
  );
}

export function useLocation(): [string, (to: string) => void] {
  const router = useRouter();
  const pathname = usePathname();
  return [pathname, (to: string) => router.push(to)];
}

export function useParams<T extends Record<string, string> = Record<string, string>>(): T {
  return useNextParams() as T;
}

// wouter's useRoute(pattern) -> [matches, params]. We only need the params (from the dynamic
// segment), which next/navigation already exposes via useParams() regardless of the pattern.
export function useRoute<T extends Record<string, string> = Record<string, string>>(
  _pattern: string
): [boolean, T | null] {
  const params = useNextParams() as T;
  return [Object.keys(params ?? {}).length > 0, params ?? null];
}
