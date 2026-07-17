import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getContestsIndex,
  getPlayerSearchPrefix,
  getSchools,
  type ContestIndexEntry,
  type SchoolRow,
} from '../../lib/data'
import {
  filterPlayerSearchEntries,
  type PlayerSearchEntry,
} from '../../lib/search'
import { useDebounce } from '../../lib/useDebounce'
import { SearchIcon } from './primitives'

const DEBOUNCE_MS = 180
const MAX_PER_GROUP = 6

interface PlayerHit {
  kind: 'player'
  key: string
  title: string
  meta: string
}

interface SchoolHit {
  kind: 'school'
  org: string
  title: string
  meta: string
}

interface ContestHit {
  kind: 'contest'
  slug: string
  title: string
  meta: string
}

type Hit = SchoolHit | PlayerHit | ContestHit

interface SearchSchool {
  org: string
  rating: number
  contests: number
  hay: string
}
interface SearchContest {
  slug: string
  title: string
  category: string
  hay: string
}

function toSearchSchool(s: SchoolRow): SearchSchool {
  return { org: s.org, rating: s.rating, contests: s.contests, hay: s.org.toLowerCase() }
}
function toSearchContest(c: ContestIndexEntry): SearchContest {
  return { slug: c.slug, title: c.title, category: c.category, hay: `${c.title}${c.category}`.toLowerCase() }
}

function matchSchools(schools: SearchSchool[], q: string): SchoolHit[] {
  const hits: SchoolHit[] = []
  for (const s of schools) {
    if (s.hay.includes(q)) {
      hits.push({
        kind: 'school',
        org: s.org,
        title: s.org,
        meta: `学校 · ${Math.round(s.rating)} 分 · ${s.contests} 场`,
      })
      if (hits.length >= MAX_PER_GROUP) break
    }
  }
  return hits
}

function matchContests(contests: SearchContest[], q: string): ContestHit[] {
  const hits: ContestHit[] = []
  for (const c of contests) {
    if (c.hay.includes(q)) {
      hits.push({ kind: 'contest', slug: c.slug, title: c.title, meta: c.category })
      if (hits.length >= MAX_PER_GROUP) break
    }
  }
  return hits
}

/**
 * Global search styled per the Light Luxury topbar. Small school/contest indexes
 * load on focus; the player index loads one prefix shard per debounced query.
 */
export function SearchBox({ placeholder = '搜索选手、学校或比赛…' }: { placeholder?: string }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const [playerResult, setPlayerResult] = useState<{
    query: string
    rows: PlayerSearchEntry[]
  } | null>(null)
  const [schools, setSchools] = useState<SearchSchool[] | null>(null)
  const [contests, setContests] = useState<SearchContest[] | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const debounced = useDebounce(query.trim(), DEBOUNCE_MS)

  useEffect(() => {
    if (!open) return
    if (schools === null)
      getSchools().then((r) => setSchools(r.map(toSearchSchool))).catch(() => setSchools([]))
    if (contests === null)
      getContestsIndex().then((r) => setContests(r.map(toSearchContest))).catch(() => setContests([]))
  }, [open, schools, contests])

  useEffect(() => {
    if (!open || debounced.length === 0) return
    let active = true
    getPlayerSearchPrefix(debounced)
      .then((rows) => {
        if (active) setPlayerResult({ query: debounced, rows })
      })
      .catch(() => {
        if (active) setPlayerResult({ query: debounced, rows: [] })
      })
    return () => {
      active = false
    }
  }, [open, debounced])

  const players =
    playerResult?.query === debounced ? playerResult.rows : null

  useEffect(() => {
    if (!open) return
    function onClick(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const { hits } = useMemo(() => {
    if (debounced.length === 0) return { hits: [] as Hit[] }
    // Lowercase the query once; rows carry a precomputed lowercased haystack.
    const q = debounced.toLowerCase()
    // Schools first so typing a school name surfaces its page above the (often
    // many) players that share its org; player-name queries match no school.
    const sh = schools ? matchSchools(schools, q) : []
    const ph = players
      ? filterPlayerSearchEntries(players, q, MAX_PER_GROUP).map<PlayerHit>((p) => ({
          kind: 'player',
          key: p.key,
          title: p.name,
          meta: `${p.org} · ${p.contests} 场`,
        }))
      : []
    const ch = contests ? matchContests(contests, q) : []
    return { hits: [...sh, ...ph, ...ch] as Hit[] }
  }, [debounced, schools, players, contests])

  const safeActive = hits.length === 0 ? 0 : Math.min(activeIndex, hits.length - 1)

  function go(hit: Hit) {
    setOpen(false)
    setQuery('')
    if (hit.kind === 'player') navigate(`/player/${encodeURIComponent(hit.key)}`)
    else if (hit.kind === 'school') navigate(`/school/${encodeURIComponent(hit.org)}`)
    else navigate(`/contest/${hit.slug}`)
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      setOpen(false)
      return
    }
    if (hits.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((safeActive + 1) % hits.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((safeActive - 1 + hits.length) % hits.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      const hit = hits[safeActive]
      if (hit) go(hit)
    }
  }

  const showPanel = open && debounced.length > 0

  return (
    <div className="search" ref={containerRef}>
      <SearchIcon />
      <input
        placeholder={placeholder}
        aria-label="搜索选手、学校或比赛"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setActiveIndex(0)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        role="combobox"
        aria-expanded={showPanel}
        aria-controls="search-results"
        aria-autocomplete="list"
      />
      {showPanel ? (
        <div className="search__menu" id="search-results" role="listbox">
          {hits.length === 0 ? (
            <p className="search__empty">
              {players === null ? '搜索索引加载中…' : '未找到匹配结果'}
            </p>
          ) : (
            hits.map((hit, idx) => (
              <button
                key={
                  hit.kind === 'player'
                    ? `p-${hit.key}`
                    : hit.kind === 'school'
                      ? `s-${hit.org}`
                      : `c-${hit.slug}`
                }
                type="button"
                role="option"
                aria-selected={idx === safeActive}
                className={`search__item ${idx === safeActive ? 'is-active' : ''}`}
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => go(hit)}
              >
                <b>{hit.title}</b>
                <span className="meta">
                  {hit.kind === 'contest' ? `比赛 · ${hit.meta}` : hit.meta}
                </span>
              </button>
            ))
          )}
        </div>
      ) : null}
    </div>
  )
}
