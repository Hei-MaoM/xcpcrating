import { useEffect, useRef, useState } from 'react'
import { Caret } from '../../components/ui'

/*
 * A small themed calendar popover for picking the 时间段 board's end date. The
 * native <input type="date"> can't theme its popup, so this hand-rolled month
 * grid keeps the Light Luxury look consistent. Day-precise, bounded to the data
 * range, closes on outside click / Escape.
 */

interface EndDatePickerProps {
  /** Selected end date as `YYYY-MM-DD`. */
  value: string
  /** Earliest / latest selectable date (`YYYY-MM-DD`), inclusive. */
  min: string
  max: string
  onChange: (next: string) => void
  disabled?: boolean
}

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'] as const

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

/** `YYYY-MM-DD` for a (year, 1-based month, day) triple. */
function iso(year: number, month: number, day: number): string {
  return `${year}-${pad(month)}-${pad(day)}`
}

/** Parse `YYYY-MM-DD` into a {year, month, day} triple (month 1-based). */
function parse(value: string): { year: number; month: number; day: number } {
  const [year, month, day] = value.split('-').map(Number)
  return { year, month, day }
}

/** Days in a 1-based month; trailing 0 day rolls back to the month's last day. */
function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate()
}

/** Weekday (0=Sun) of the first day of a 1-based month. */
function firstWeekday(year: number, month: number): number {
  return new Date(year, month - 1, 1).getDay()
}

export function EndDatePicker({
  value,
  min,
  max,
  onChange,
  disabled,
}: EndDatePickerProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const selected = parse(value)
  // The month currently shown; re-synced to the selection each time we open.
  const [view, setView] = useState({ year: selected.year, month: selected.month })

  // Opening jumps the calendar to the selected month (no effect needed — we know
  // the transition right here, so there are no cascading renders to lint about).
  function toggle() {
    if (!open) setView({ year: selected.year, month: selected.month })
    setOpen((o) => !o)
  }

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  const minP = parse(min)
  const maxP = parse(max)
  // Month-level bounds: a month step is blocked once it would leave [min, max].
  const atMinMonth =
    view.year < minP.year ||
    (view.year === minP.year && view.month <= minP.month)
  const atMaxMonth =
    view.year > maxP.year ||
    (view.year === maxP.year && view.month >= maxP.month)
  const atMinYear = view.year <= minP.year
  const atMaxYear = view.year >= maxP.year

  function stepMonth(delta: number) {
    setView((v) => {
      const m = v.month + delta
      if (m < 1) return { year: v.year - 1, month: 12 }
      if (m > 12) return { year: v.year + 1, month: 1 }
      return { year: v.year, month: m }
    })
  }

  function stepYear(delta: number) {
    setView((v) => ({ year: v.year + delta, month: v.month }))
  }

  function pick(day: number) {
    onChange(iso(view.year, view.month, day))
    setOpen(false)
  }

  const total = daysInMonth(view.year, view.month)
  const lead = firstWeekday(view.year, view.month)
  // 6-row grid: leading blanks for the first weekday, then the month's days.
  const cells: Array<number | null> = [
    ...Array.from({ length: lead }, () => null),
    ...Array.from({ length: total }, (_, i) => i + 1),
  ]

  return (
    <div className="datepick" ref={ref}>
      <button
        type="button"
        className="datepick__trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        disabled={disabled}
        onClick={toggle}
      >
        <svg
          className="datepick__icon"
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <rect x="3" y="4.5" width="18" height="16" rx="2.5" stroke="currentColor" strokeWidth="1.6" />
          <path d="M3 9h18M8 2.5v4M16 2.5v4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <span className="datepick__tag">截至</span>
        <span className="datepick__value">{value.replace(/-/g, '/')}</span>
        <span className="datepick__caret">
          <Caret dir={open ? 'up' : 'down'} />
        </span>
      </button>

      {open ? (
        <div className="datepick__panel" role="dialog" aria-label="选择结束日期">
          <div className="datepick__head">
            <button
              type="button"
              className="datepick__nav"
              aria-label="上一年"
              disabled={atMinYear}
              onClick={() => stepYear(-1)}
            >
              «
            </button>
            <button
              type="button"
              className="datepick__nav"
              aria-label="上个月"
              disabled={atMinMonth}
              onClick={() => stepMonth(-1)}
            >
              ‹
            </button>
            <span className="datepick__title">
              {view.year} 年 {view.month} 月
            </span>
            <button
              type="button"
              className="datepick__nav"
              aria-label="下个月"
              disabled={atMaxMonth}
              onClick={() => stepMonth(1)}
            >
              ›
            </button>
            <button
              type="button"
              className="datepick__nav"
              aria-label="下一年"
              disabled={atMaxYear}
              onClick={() => stepYear(1)}
            >
              »
            </button>
          </div>

          <div className="datepick__wdrow">
            {WEEKDAYS.map((w) => (
              <span key={w} className="datepick__wd">
                {w}
              </span>
            ))}
          </div>

          <div className="datepick__grid">
            {cells.map((day, i) => {
              if (day === null)
                return <span key={`b${i}`} className="datepick__cell" />
              const dateStr = iso(view.year, view.month, day)
              const outOfRange = dateStr < min || dateStr > max
              const isSelected = dateStr === value
              return (
                <button
                  key={dateStr}
                  type="button"
                  className={`datepick__day ${isSelected ? 'is-selected' : ''}`}
                  disabled={outOfRange}
                  aria-pressed={isSelected}
                  onClick={() => pick(day)}
                >
                  {day}
                </button>
              )
            })}
          </div>
        </div>
      ) : null}
    </div>
  )
}
