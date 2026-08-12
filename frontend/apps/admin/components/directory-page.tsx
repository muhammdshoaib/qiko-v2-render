"use client";

import { Suspense, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import {
  Alert, Card, CardContent, DataTable, Input, Pagination, Skeleton, type Column, type SortOrder,
} from "@qiko/ui";
import { AppShell } from "@/components/app-shell";
import { adminMe, type ListSort } from "@/lib/api";

const PAGE_SIZE = 20;

type Props<T> = {
  title: string;
  searchLabel: string;
  searchPlaceholder: string;
  queryKey: string;
  /** Plural noun for the rows, used in the pagination announcement. */
  noun: string;
  fetchPage: (search: string, page: number, sort?: ListSort) =>
    Promise<{ total: number; page: number; items: T[] }>;
  columns: Column<T>[];
  rowKey: (row: T) => string;
  /** Card body for narrow viewports. Falls back to the columns when absent. */
  renderCard?: (row: T) => ReactNode;
  actions?: (row: T) => ReactNode;
  // Called with whether a search or filter is narrowing the view, because "No workers match this
  // filter" was shown even when the platform genuinely had zero workers, and vice versa.
  emptyMessage: (filtered: boolean) => string;
  filters?: ReactNode;
  /** Included in the query key so a filter change refetches. */
  filterToken?: string;
  onClearFilters?: () => void;
  /** The default sort, matching whatever order the endpoint returns when none is requested. */
  defaultSort?: ListSort;
};

/**
 * The shared shape of the cross-tenant directories.
 *
 * What changed here, and why it is one file rather than five: the console rendered every list as a
 * stack of cards, so there were no column headers, nothing was sortable, and a screen reader received
 * an unlabelled stream of values. The backend has accepted sort, order and page_size on all five of
 * these endpoints since leg B and no page ever sent one, which meant a validated, allowlisted sort
 * existed on the server and was unreachable from the product.
 *
 * Search, page and sort now live in the URL. A directory link is the thing operators paste into a
 * ticket, and a page whose state is invisible to the address bar cannot be shared. It also makes the
 * back button behave, which card lists with internal state never did.
 */
function Directory<T>({
  title, searchLabel, searchPlaceholder, queryKey, noun, fetchPage, columns, rowKey,
  renderCard, actions, emptyMessage, filters, filterToken = "", onClearFilters, defaultSort,
}: Props<T>) {
  const router = useRouter();
  const params = useSearchParams();

  const urlSearch = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page") ?? 1));
  const sortKey = params.get("sort") ?? defaultSort?.sort ?? "";
  const order = (params.get("order") ?? defaultSort?.order ?? "asc") as SortOrder;

  // The input is the one piece of local state, because it has to stay responsive between keystrokes.
  // The URL is updated on a debounce, which is also what resets the page.
  const [typed, setTyped] = useState(urlSearch);

  const setParam = useCallback((updates: Record<string, string>) => {
    const next = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(updates)) {
      if (value) next.set(key, value); else next.delete(key);
    }
    router.replace(`?${next.toString()}`, { scroll: false });
  }, [params, router]);

  useEffect(() => {
    if (typed === urlSearch) return;
    const timer = window.setTimeout(() => {
      // A search change must reset to page 1, or the operator lands on an empty page and reads it as
      // "no results" when there are results on page 1.
      setParam({ q: typed.trim(), page: "" });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [typed, urlSearch, setParam]);

  useEffect(() => { setTyped(urlSearch); }, [urlSearch]);

  const sort = useMemo<ListSort | undefined>(
    () => (sortKey ? { sort: sortKey, order } : undefined), [sortKey, order]);

  const me = useQuery({ queryKey: ["admin-me"], queryFn: adminMe });
  const rows = useQuery({
    queryKey: [queryKey, urlSearch, page, filterToken, sortKey, order],
    queryFn: () => fetchPage(urlSearch, page, sort),
    // Gated on the capability check, which is what creates the trap below: a DISABLED query reports
    // isLoading false in React Query v5, because it is not loading, it simply has not started.
    enabled: me.isSuccess,
    // Without this, the query key change on every page, sort or filter click made isLoading true again
    // and the whole list collapsed into skeleton bars.
    placeholderData: keepPreviousData,
  });

  // "Nothing has arrived yet" is not the same as "isLoading". Until the capability check resolves the
  // rows query has not started, so isLoading is false and rows.data is undefined, and rendering the
  // empty state on that combination makes the page assert there are no customers before it has asked.
  // A slow connection showed "No customers yet" and then the list, and the server-rendered HTML said it
  // outright, which is how this was found: React reported the hydration mismatch between the server's
  // empty state and the client's skeletons.
  //
  // An empty state that lies is worse than a spinner, and this is the third time in this console the
  // same mistake has appeared in a different shape.
  const awaitingFirstAnswer = !me.isSuccess || rows.isLoading || (rows.isPending && !rows.data);

  const total = rows.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const shown = rows.data?.items.length ?? 0;
  const firstOnPage = shown === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const narrowed = Boolean(urlSearch) || filterToken !== "";

  return (
    <AppShell title={title}>
      <div className="mx-auto max-w-6xl space-y-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight" style={{ fontFamily: "var(--font-display)" }}>{title}</h1>
            {/* A range rather than a bare total: "137 total" is identical before and after a filter
                that returns the same count of a different set, so a live region announces nothing. */}
            <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
              {awaitingFirstAnswer ? `Loading ${noun}...`
                : rows.data ? `Showing ${firstOnPage}-${(page - 1) * PAGE_SIZE + shown} of ${total} ${noun}`
                  : "Unavailable"}
            </p>
          </div>
          <label className="relative w-full sm:w-72">
            <span className="sr-only">{searchLabel}</span>
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input className="pl-9" placeholder={searchPlaceholder} value={typed}
              onChange={(event) => setTyped(event.target.value)} />
          </label>
        </div>

        {filters}

        {me.isError && (
          <Alert tone="error">
            Couldn&apos;t verify Admin access.{" "}
            <button className="underline" onClick={() => me.refetch()}>Retry</button>
          </Alert>
        )}
        {rows.isError && (
          <Alert tone="error">
            Couldn&apos;t load {title.toLowerCase()}.{" "}
            <button className="underline" onClick={() => rows.refetch()}>Retry</button>
          </Alert>
        )}

        {awaitingFirstAnswer
          ? <div className="space-y-2">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
          : (
            <DataTable
              caption={`${title}, ${sortKey ? `sorted by ${sortKey}` : "in the default order"}`}
              columns={columns}
              rows={rows.data?.items ?? []}
              rowKey={rowKey}
              renderCard={renderCard}
              actions={actions}
              sort={sortKey || null}
              order={order}
              // A sort change resets to page 1: page 3 of one ordering is not page 3 of another, and
              // landing mid-list after re-sorting reads as missing rows.
              onSortChange={(nextSort, nextOrder) =>
                setParam({ sort: nextSort, order: nextOrder, page: "" })}
              stale={rows.isPlaceholderData}
              empty={
                <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">
                  {emptyMessage(narrowed)}
                  {narrowed && onClearFilters && (
                    <div>
                      <button className="mt-3 underline" onClick={onClearFilters}>Clear filters</button>
                    </div>
                  )}
                </CardContent></Card>
              }
            />
          )}

        {pageCount > 1 && (
          <Pagination page={page} pageCount={pageCount} total={total} shown={shown} label={noun}
            busy={rows.isFetching}
            onChange={(next) => setParam({ page: next === 1 ? "" : String(next) })} />
        )}
      </div>
    </AppShell>
  );
}

export function DirectoryPage<T>(props: Props<T>) {
  // useSearchParams needs a Suspense boundary in the app router.
  return <Suspense fallback={null}><Directory<T> {...props} /></Suspense>;
}
