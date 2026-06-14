import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getContestsIndex,
  getPlayersIndex,
  type ContestIndexEntry,
  type PlayerIndexEntry,
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

interface ContestHit {
  kind: 'contest'
  slug: string
  title: string
  meta: string
}

type Hit = PlayerHit | ContestHit

function matchPlayers(players: PlayerIndexEntry[], query: string): PlayerHit[] {
  const q = query.toLowerCase()
  const hits: PlayerHit[] = []
  for (const p of players) {
    if (p.name.toLowerCase().includes(q) || p.org.toLowerCase().includes(q)) {
      hits.push({
        kind: 'player',
        key: p.key,
        title: p.name,
        meta: `${p.org} · ${p.contests} 场`,
      })
      if (hits.length >= MAX_PER_GROUP) break
    }
  }
  return hits
}

function matchContests(contests: ContestIndexEntry[], query: string): ContestHit[] {
  const q = query.toLowerCase()
  const hits: ContestHit[] = []
  for (const c of contests) {
    if (c.title.toLowerCase().includes(q) || c.category.toLowerCase().includes(q)) {
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
  const [players, setPlayers] = useState<PlayerIndexEntry[] | null>(null)
  const [contests, setContests] = useState<ContestIndexEntry[] | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const debounced = useDebounce(query.trim(), DEBOUNCE_MS)

  useEffect(() => {
    if (!open) return
    if (players === null) getPlayersIndex().then(setPlayers).catch(() => setPlayers([]))
    if (contests === null) getContestsIndex().then(setContests).catch(() => setContests([]))
  }, [open, players, contests])

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
    const ph = players ? matchPlayers(players, debounced) : []
    const ch = contests ? matchContests(contests, debounced) : []
    return { hits: [...ph, ...ch] as Hit[] }
  }, [debounced, players, contests])

  const safeActive = hits.length === 0 ? 0 : Math.min(activeIndex, hits.length - 1)

  function go(hit: Hit) {
    setOpen(false)
    setQuery('')
    if (hit.kind === 'player') navigate(`/player/${encodeURIComponent(hit.key)}`)
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
                key={hit.kind === 'player' ? `p-${hit.key}` : `c-${hit.slug}`}
                type="button"
                role="option"
                aria-selected={idx === safeActive}
                className={`search__item ${idx === safeActive ? 'is-active' : ''}`}
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => go(hit)}
              >
                <b>{hit.title}</b>
                <span className="meta">
                  {hit.kind === 'player' ? hit.meta : `比赛 · ${hit.meta}`}
                </span>
              </button>
            ))
          )}
        </div>
      ) : null}
    </div>
  )
}
