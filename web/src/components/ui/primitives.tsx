/*
 * Shared Light Luxury design primitives (icons, count-up, reveal-on-scroll,
 * hairline draw-in, delta / deviation chips, medal pip group). Pure
 * presentation — no data I/O.
 */
import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'

/** True when the user asked the OS to minimise motion. */
export function prefersReduced(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/* ------------------------------------------------------------------ *
 * Icons
 * ------------------------------------------------------------------ */

export function SearchIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M11 11l3.5 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  )
}

type CaretDir = 'down' | 'up' | 'left' | 'right'
export function Caret({ dir = 'down', size = 12 }: { dir?: CaretDir; size?: number }) {
  const r = { down: 0, up: 180, left: 90, right: -90 }[dir]
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="none" style={{ transform: `rotate(${r}deg)` }} aria-hidden="true">
      <path d="M2.5 4.5L6 8l3.5-3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/* ------------------------------------------------------------------ *
 * Count-up — animates a number from 0 to target when scrolled into view
 * ------------------------------------------------------------------ */

interface CountUpProps {
  value: number
  decimals?: number
  duration?: number
  className?: string
}

export function CountUp({ value, decimals = 0, duration = 1100, className }: CountUpProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const [display, setDisplay] = useState(() => (prefersReduced() ? value : 0))

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (prefersReduced()) {
      setDisplay(value)
      return
    }
    let raf = 0
    let t0 = 0
    const ease = (t: number) => 1 - Math.pow(1 - t, 3)
    const run = () => {
      const tick = (t: number) => {
        if (!t0) t0 = t
        const p = Math.min(1, (t - t0) / duration)
        setDisplay(value * ease(p))
        if (p < 1) raf = requestAnimationFrame(tick)
        else setDisplay(value)
      }
      raf = requestAnimationFrame(tick)
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          run()
          io.disconnect()
        }
      },
      { threshold: 0.4 },
    )
    io.observe(el)
    return () => {
      io.disconnect()
      cancelAnimationFrame(raf)
    }
  }, [value, duration])

  const text = Number(display).toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    useGrouping: false,
  })
  return (
    <span ref={ref} className={className}>
      {text}
    </span>
  )
}

/* ------------------------------------------------------------------ *
 * Reveal — fades + lifts children in when they scroll into view
 * ------------------------------------------------------------------ */

interface RevealProps {
  children: ReactNode
  className?: string
  delay?: number
  as?: 'div' | 'section' | 'li'
  onClick?: () => void
  onKeyDown?: (e: React.KeyboardEvent) => void
  tabIndex?: number
  role?: string
}

export function Reveal({
  children,
  className = '',
  delay = 0,
  as: Tag = 'div',
  ...rest
}: RevealProps) {
  const ref = useRef<HTMLElement>(null)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (prefersReduced()) {
      setShown(true)
      return
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setShown(true)
          io.disconnect()
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const Component = Tag as any
  return (
    <Component
      ref={ref}
      className={`reveal ${shown ? 'is-in' : ''} ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
      {...rest}
    >
      {children}
    </Component>
  )
}

/** A hairline rule that "draws in" (oxford wipe) when scrolled into view. */
export function RuleDraw({ className = '' }: { className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (prefersReduced()) {
      setShown(true)
      return
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setShown(true)
          io.disconnect()
        }
      },
      { threshold: 0.6 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return <div ref={ref} className={`rule-draw ${shown ? 'is-in' : ''} ${className}`} />
}

/* ------------------------------------------------------------------ *
 * Delta / deviation chips — colorblind-safe up / down / flat
 * ------------------------------------------------------------------ */

export function Delta({ value, decimals = 1 }: { value: number | null | undefined; decimals?: number }) {
  if (value === null || value === undefined || value === 0) {
    return <span className="delta delta--flat">—</span>
  }
  const up = value > 0
  const sign = up ? '+' : '−'
  const abs = Math.abs(value).toFixed(decimals)
  return (
    <span className={`delta ${up ? 'delta--up' : 'delta--down'}`}>
      <span className="tri">{up ? '▲' : '▼'}</span>
      {sign}
      {abs}
    </span>
  )
}

/** Prediction deviation chip: a signed rank gap with Chinese label. */
export function Deviation({ dev }: { dev: number | null }) {
  if (dev === null) return <span className="delta delta--flat">—</span>
  if (dev === 0) return <span className="delta delta--flat">— 与预期一致</span>
  const up = dev > 0
  return (
    <span className={`delta ${up ? 'delta--up' : 'delta--down'}`}>
      <span className="tri">{up ? '▲' : '▼'}</span>
      {up ? `超预期 ${dev} 名` : `低于预期 ${Math.abs(dev)} 名`}
    </span>
  )
}

/* ------------------------------------------------------------------ *
 * Medal pip group — gold / silver / bronze metal discs + counts
 * ------------------------------------------------------------------ */

interface MedalGroupProps {
  gold: number
  silver: number
  bronze: number
  size?: number
}

export function MedalGroup({ gold, silver, bronze, size = 13 }: MedalGroupProps) {
  const pip = (n: number, cls: string, label: string) => (
    <span className="medal-pip" title={label} style={{ opacity: n === 0 ? 0.32 : 1 }}>
      <i className={`metal metal--${cls}`} style={{ width: size, height: size }} />
      <span className={`medal-pip__n ${n === 0 ? 'is-zero' : ''}`}>{n}</span>
    </span>
  )
  return (
    <span className="medal-group">
      {pip(gold, 'gold', '金')}
      {pip(silver, 'silver', '银')}
      {pip(bronze, 'bronze', '铜')}
    </span>
  )
}
