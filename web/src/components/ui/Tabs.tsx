import type { ReactNode } from 'react'

export interface TabItem<T extends string = string> {
  value: T
  label: ReactNode
}

interface TabsProps<T extends string> {
  items: TabItem<T>[]
  value: T
  onChange: (value: T) => void
  ariaLabel?: string
}

/**
 * Underlined tab bar. Controlled: the parent owns the active value (so it can
 * sync to the URL). Roving via native buttons keeps keyboard access simple.
 */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  ariaLabel,
}: TabsProps<T>) {
  return (
    <div className="tabs" role="tablist" aria-label={ariaLabel}>
      {items.map((item) => {
        const isActive = item.value === value
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={isActive}
            className={`tabs__tab${isActive ? ' tabs__tab--active' : ''}`}
            onClick={() => onChange(item.value)}
          >
            {item.label}
          </button>
        )
      })}
    </div>
  )
}
