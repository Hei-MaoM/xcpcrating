import type { ReactNode } from 'react'

export type BadgeVariant =
  | 'neutral'
  | 'accent'
  | 'gold'
  | 'silver'
  | 'bronze'
  | 'up'
  | 'down'

interface BadgeProps {
  variant?: BadgeVariant
  children: ReactNode
  title?: string
}

/** Small pill label. Medal variants carry podium semantics only. */
export function Badge({ variant = 'neutral', children, title }: BadgeProps) {
  return (
    <span className={`badge badge--${variant}`} title={title}>
      {children}
    </span>
  )
}
