import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * Leaderboard URL state lives entirely in the query string so a view is
 * shareable and survives reloads:
 *   ?page=<1-based>            current page
 *   ?org=<school>              optional same-school filter
 *
 * There is a single board now; any stale `?engine=` param from an old link is
 * simply ignored (never read, never written). Defaults (page 1, no filter) are
 * omitted from the URL to keep it clean. Updates are immutable: we always build
 * a fresh URLSearchParams.
 */

export interface LeaderboardParams {
  page: number
  org: string | null
}

function parsePage(raw: string | null): number {
  const n = Number(raw)
  return Number.isInteger(n) && n >= 1 ? n : 1
}

export interface LeaderboardParamsApi extends LeaderboardParams {
  setPage: (page: number) => void
  setOrg: (org: string | null) => void
}

export function useLeaderboardParams(): LeaderboardParamsApi {
  const [searchParams, setSearchParams] = useSearchParams()

  const page = parsePage(searchParams.get('page'))
  const orgRaw = searchParams.get('org')
  const org = orgRaw && orgRaw.trim() !== '' ? orgRaw : null

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
          }

          // Drop any legacy engine selector silently.
          merged.delete('engine')

          if (resolved.page <= 1) merged.delete('page')
          else merged.set('page', String(resolved.page))

          if (!resolved.org) merged.delete('org')
          else merged.set('org', resolved.org)

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

  return useMemo(
    () => ({ page, org, setPage, setOrg }),
    [page, org, setPage, setOrg],
  )
}
