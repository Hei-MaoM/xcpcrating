import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * Leaderboard URL state lives entirely in the query string so a view is
 * shareable and survives reloads:
 *   ?page=<1-based>            current page
 *   ?org=<school>              optional same-school filter
 *   ?to=<YYYY-MM-DD>           时间段 board end date (period view only)
 *
 * There is a single board now; any stale `?engine=` param from an old link is
 * simply ignored (never read, never written). Defaults (page 1, no filter) are
 * omitted from the URL to keep it clean. Updates are immutable: we always build
 * a fresh URLSearchParams.
 */

export interface LeaderboardParams {
  page: number
  org: string | null
  to: string | null
}

function parsePage(raw: string | null): number {
  const n = Number(raw)
  return Number.isInteger(n) && n >= 1 ? n : 1
}

/** Keep only well-formed `YYYY-MM-DD` date params; anything else reads as null. */
function parseDate(raw: string | null): string | null {
  return raw && /^\d{4}-\d{2}-\d{2}$/.test(raw) ? raw : null
}

export interface LeaderboardParamsApi extends LeaderboardParams {
  setPage: (page: number) => void
  setOrg: (org: string | null) => void
  setTo: (to: string | null) => void
}

export function useLeaderboardParams(): LeaderboardParamsApi {
  const [searchParams, setSearchParams] = useSearchParams()

  const page = parsePage(searchParams.get('page'))
  const orgRaw = searchParams.get('org')
  const org = orgRaw && orgRaw.trim() !== '' ? orgRaw : null
  const to = parseDate(searchParams.get('to'))

  // Build the next query from the current snapshot, then prune defaults. A stale
  // `engine` param is dropped here so chasing it out of old bookmarks is free.
  const patch = useCallback(
    (next: Partial<LeaderboardParams>) => {
      setSearchParams(
        (prev) => {
          const merged = new URLSearchParams(prev)
          const resolved: LeaderboardParams = {
            page: next.page ?? parsePage(prev.get('page')),
            org:
              next.org !== undefined
                ? next.org
                : (prev.get('org') ?? null) || null,
            to: next.to !== undefined ? next.to : parseDate(prev.get('to')),
          }

          // Drop any legacy engine / from selector silently.
          merged.delete('engine')
          merged.delete('from')

          if (resolved.page <= 1) merged.delete('page')
          else merged.set('page', String(resolved.page))

          if (!resolved.org) merged.delete('org')
          else merged.set('org', resolved.org)

          if (!resolved.to) merged.delete('to')
          else merged.set('to', resolved.to)

          return merged
        },
        { replace: false },
      )
    },
    [setSearchParams],
  )

  const setPage = useCallback((nextPage: number) => patch({ page: nextPage }), [
    patch,
  ])
  const setOrg = useCallback(
    // Changing the org filter resets to the first page of the new result set.
    (nextOrg: string | null) => patch({ org: nextOrg, page: 1 }),
    [patch],
  )
  // Moving the end date re-shapes the result set → back to page 1.
  const setTo = useCallback(
    (nextTo: string | null) => patch({ to: nextTo, page: 1 }),
    [patch],
  )

  return useMemo(
    () => ({ page, org, to, setPage, setOrg, setTo }),
    [page, org, to, setPage, setOrg, setTo],
  )
}
