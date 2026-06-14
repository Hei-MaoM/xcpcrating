import { useEffect, useMemo, useRef, useState } from 'react'
import { Caret, SearchIcon } from '../../components/ui'
import {
  filterSchoolOptions,
  type SchoolOption,
} from './schools'

interface SchoolFilterProps {
  /** Currently selected school org, or null for "all schools". */
  value: string | null
  options: ReadonlyArray<SchoolOption>
  onChange: (org: string | null) => void
  disabled?: boolean
}

const ALL_LABEL = '全部学校'

/**
 * Light Luxury searchable school dropdown. Schools can number in the thousands,
 * so the menu carries its own search input that narrows the list as you type;
 * Enter selects the first match, Escape closes.
 */
export function SchoolFilter({ value, options, onChange, disabled }: SchoolFilterProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setQuery('')
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  const filtered = useMemo(
    () => filterSchoolOptions(options, query),
    [options, query],
  )
  const term = query.trim()
  const showAll = term === '' || ALL_LABEL.includes(term)

  function pick(org: string | null) {
    onChange(org)
    setOpen(false)
    setQuery('')
  }

  return (
    <div className="ddl" ref={ref}>
      <button
        className="btn"
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
      >
        <span>{value ?? ALL_LABEL}</span>
        <span className="caret">
          <Caret dir={open ? 'up' : 'down'} />
        </span>
      </button>
      {open ? (
        <div className="menu">
          <div className="menu__search">
            <SearchIcon size={14} />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索学校…"
              aria-label="搜索学校"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && filtered.length) pick(filtered[0].org)
                if (e.key === 'Escape') {
                  setOpen(false)
                  setQuery('')
                }
              }}
            />
          </div>
          <div className="menu__list" role="listbox">
            {showAll ? (
              <button
                role="option"
                aria-selected={value === null}
                className={`menu__item ${value === null ? 'is-sel' : ''}`}
                onClick={() => pick(null)}
              >
                {ALL_LABEL}
                {value === null ? <span className="menu__tick">✓</span> : null}
              </button>
            ) : null}
            {filtered.map((opt) => (
              <button
                key={opt.org}
                role="option"
                aria-selected={opt.org === value}
                className={`menu__item ${opt.org === value ? 'is-sel' : ''}`}
                onClick={() => pick(opt.org)}
              >
                <span>{opt.org}</span>
                {opt.org === value ? (
                  <span className="menu__tick">✓</span>
                ) : (
                  <span className="menu__count">{opt.count}</span>
                )}
              </button>
            ))}
            {!showAll && filtered.length === 0 ? (
              <div className="menu__empty">无匹配学校</div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}
