import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getContestsIndex,
  getPlayersIndex,
  getSchools,
  type ContestIndexEntry,
  type PlayerIndexEntry,
  type SchoolRow,
} from '../../lib/data'
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

/*
 * Search-optimized rows: the lowercased haystack (`hay`) is precomputed once when
 * the index loads, so filtering 60k+ players on every keystroke is a single
 * `includes` per row instead of two `toLowerCase()` allocations per row.
 */
interface SearchPlayer {
  key: string
  name: string
  org: string
  contests: number
  hay: string
}
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

function toSearchPlayer(p: PlayerIndexEntry): SearchPlayer {
  return { key: p.key, name: p.name, org: p.org, contests: p.contests, hay: `${p.name}${p.org}`.toLowerCase() }
}
function toSearchSchool(s: SchoolRow): SearchSchool {
  return { org: s.org, rating: s.rating, contests: s.contests, hay: s.org.toLowerCase() }
}
function toSearchContest(c: ContestIndexEntry): SearchContest {
  return { slug: c.slug, title: c.title, category: c.category, hay: `${c.title}${c.category}`.toLowerCase() }
}

// `q` is already lowercased/trimmed by the caller.
function matchPlayers(players: SearchPlayer[], q: string): PlayerHit[] {
  const hits: PlayerHit[] = []
  for (const p of players) {
    if (p.hay.includes(q)) {
      hits.push({ kind: 'player', key: p.key, title: p.name, meta: `${p.org} · ${p.contests} 场` })
      if (hits.length >= MAX_PER_GROUP) break
    }
  }
  return hits
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
 * Global search styled per the Light Luxury topbar. Lazily loads the player and
 * contest indexes on first focus, filters client-side, and supports arrow/enter
 * keyboard navigation. Selecting a result navigates to its detail page.
 */
export function SearchBox({ placeholder = '搜索选手、学校或比赛…' }: { placeholder?: string }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const [players, setPlayers] = useState<SearchPlayer[] | null>(null)
  const [schools, setSchools] = useState<SearchSchool[] | null>(null)
  const [contests, setContests] = useState<SearchContest[] | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const debounced = useDebounce(query.trim(), DEBOUNCE_MS)

  useEffect(() => {
    if (!open) return
    if (players === null)
      getPlayersIndex().then((r) => setPlayers(r.map(toSearchPlayer))).catch(() => setPlayers([]))
    if (schools === null)
      getSchools().then((r) => setSchools(r.map(toSearchSchool))).catch(() => setSchools([]))
    if (contests === null)
      getContestsIndex().then((r) => setContests(r.map(toSearchContest))).catch(() => setContests([]))
  }, [open, players, schools, contests])

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
    const ph = players ? matchPlayers(players, q) : []
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
            <p className="search__empty">未找到匹配结果</p>
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
