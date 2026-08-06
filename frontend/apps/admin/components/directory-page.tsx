"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { Button, Card, CardContent, Input, Skeleton } from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { adminMe } from "@/lib/api";

const PAGE_SIZE = 20;

type Props<T> = {
  title: string;
  searchLabel: string;
  searchPlaceholder: string;
  queryKey: string;
  fetchPage: (search: string, page: number) => Promise<{ total: number; page: number; items: T[] }>;
  renderRow: (row: T) => ReactNode;
  rowKey: (row: T) => string;
  // Called with whether a search or filter is narrowing the view, because "No workers match this
  // filter" was shown even when the platform genuinely had zero workers, and vice versa.
  emptyMessage: (filtered: boolean) => string;
  onClearFilters?: () => void;
  filters?: ReactNode;
  /** Included in the query key so a filter change refetches. */
  filterToken?: string;
};

/**
 * The shared shape of the three cross-tenant directories.
 *
 * Extracted rather than copied three more times: the customers page already carries the debounce,
 * the page-reset-on-search, the loading and error affordances and the pagination nav, and three
 * hand-copied variants would drift. Accessibility details (the aria-live total, the sr-only search
 * label, the aria-busy list, role="alert" retries, the labelled pagination nav) are the parts that
 * silently rot when duplicated.
 */
export function DirectoryPage<T>({
  title, searchLabel, searchPlaceholder, queryKey, fetchPage, renderRow, rowKey,
  emptyMessage, filters, filterToken = "", onClearFilters,
}: Props<T>) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const firstRender = useRef(true);

  const me = useQuery({ queryKey: ["admin-me"], queryFn: adminMe });
  const rows = useQuery({
    queryKey: [queryKey, query, page, filterToken],
    queryFn: () => fetchPage(query, page),
    enabled: me.isSuccess,
    // Without this the query key change on every page or filter click made isLoading true again and
    // the whole list collapsed into skeleton bars, which is the single most dated-feeling thing in
    // the console. Keeping the previous rows and dimming them is what current admin UIs do.
    placeholderData: keepPreviousData,
  });

  useEffect(() => {
    const timer = window.setTimeout(() => { setQuery(search.trim()); setPage(1); }, 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    // A filter change must reset to page 1, or the operator lands on an empty page and reads it as
    // "no results" when there are results on page 1.
    if (firstRender.current) { firstRender.current = false; return; }
    setPage(1);
  }, [filterToken]);

  const totalPages = Math.max(1, Math.ceil((rows.data?.total ?? 0) / PAGE_SIZE));

  return (
    <AppShell title={title}>
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>{title}</h1>
            <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
              {me.isLoading || rows.isLoading
                ? "Loading total..."
                : rows.data ? `${rows.data.total} total` : "Total unavailable"}
            </p>
          </div>
          <label className="relative w-full sm:w-72">
            <span className="sr-only">{searchLabel}</span>
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input className="min-h-11 pl-9" placeholder={searchPlaceholder} value={search}
              onChange={(event) => setSearch(event.target.value)} />
          </label>
        </div>

        {filters}

        {me.isError && (
          <Card><CardContent role="alert" className="py-6 text-sm text-destructive">
            Couldn&apos;t verify Admin access.{" "}
            <button className="underline" onClick={() => me.refetch()}>Retry</button>
          </CardContent></Card>
        )}
        {rows.isError && (
          <Card><CardContent role="alert" className="py-6 text-sm text-destructive">
            Couldn&apos;t load {title.toLowerCase()}.{" "}
            <button className="underline" onClick={() => rows.refetch()}>Retry</button>
          </CardContent></Card>
        )}

        <div className="space-y-3" aria-busy={rows.isFetching}>
          {rows.isLoading && [0, 1, 2].map((index) => <Skeleton key={index} className="h-20 w-full" />)}
          {rows.data?.items.length === 0 && (
            <Card><CardContent className="py-6 text-center text-sm text-muted-foreground">
              {emptyMessage(Boolean(query) || filterToken !== "")}
              {(Boolean(query) || filterToken !== "") && onClearFilters && (
                <div>
                  <Button variant="outline" className="mt-3 min-h-11" onClick={onClearFilters}>
                    Clear filters
                  </Button>
                </div>
              )}
            </CardContent></Card>
          )}
          {rows.data?.items.map((row) => (
            <Card key={rowKey(row)}><CardContent className="py-4">{renderRow(row)}</CardContent></Card>
          ))}
        </div>

        <nav aria-label={`${title} pagination`} className="flex items-center justify-between">
          <Button variant="outline" className="min-h-11" disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}>
            <ChevronLeft className="mr-1 size-4" aria-hidden="true" /> Previous
          </Button>
          <span className="text-sm text-muted-foreground">Page {page} of {totalPages}</span>
          <Button variant="outline" className="min-h-11" disabled={page >= totalPages}
            onClick={() => setPage((current) => current + 1)}>
            Next <ChevronRight className="ml-1 size-4" aria-hidden="true" />
          </Button>
        </nav>
      </div>
    </AppShell>
  );
}
