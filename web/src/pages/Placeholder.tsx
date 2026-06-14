import type { ReactNode } from 'react'

interface PlaceholderProps {
  eyebrow: string
  title: string
  description?: ReactNode
}

/**
 * Shared "under construction" view for scaffolded routes. Page agents replace
 * the page modules that render this; the scaffold ships it so the build and
 * navigation work end to end before the business pages land.
 */
export function Placeholder({ eyebrow, title, description }: PlaceholderProps) {
  return (
    <section className="page">
      <p className="text-eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <div className="state" role="status">
        <p className="state__title">建设中</p>
        <p>{description ?? '该页面尚未实现，敬请期待。'}</p>
      </div>
    </section>
  )
}
