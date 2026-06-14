interface PaginationProps {
  page: number // 1-based
  pageSize: number
  totalItems: number
  onPageChange: (page: number) => void
}

const SIBLINGS = 1

/** Build a compact page list with ellipses, e.g. 1 … 4 5 [6] 7 8 … 20. */
function buildPages(current: number, total: number): (number | 'gap')[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }

  const pages: (number | 'gap')[] = [1]
  const start = Math.max(2, current - SIBLINGS)
  const end = Math.min(total - 1, current + SIBLINGS)

  if (start > 2) pages.push('gap')
  for (let p = start; p <= end; p++) pages.push(p)
  if (end < total - 1) pages.push('gap')

  pages.push(total)
  return pages
}

/** Numeric pager with prev/next and ellipsis collapsing. */
export function Pagination({
  page,
  pageSize,
  totalItems,
  onPageChange,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize))
  if (totalPages <= 1) return null

  const clamped = Math.min(Math.max(1, page), totalPages)
  const from = (clamped - 1) * pageSize + 1
  const to = Math.min(clamped * pageSize, totalItems)
  const pages = buildPages(clamped, totalPages)

  return (
    <nav className="pagination" aria-label="分页">
      <span className="pagination__summary tnum">
        第 {from}–{to} 项，共 {totalItems} 项
      </span>
      <div className="pagination__controls">
        <button
          type="button"
          className="pagination__btn"
          onClick={() => onPageChange(clamped - 1)}
          disabled={clamped <= 1}
          aria-label="上一页"
        >
          ‹
        </button>
        {pages.map((p, i) =>
          p === 'gap' ? (
            <span key={`gap-${i}`} className="pagination__ellipsis">
              …
            </span>
          ) : (
            <button
              key={p}
              type="button"
              className={`pagination__btn${
                p === clamped ? ' pagination__btn--active' : ''
              }`}
              onClick={() => onPageChange(p)}
              aria-current={p === clamped ? 'page' : undefined}
            >
              {p}
            </button>
          ),
        )}
        <button
          type="button"
          className="pagination__btn"
          onClick={() => onPageChange(clamped + 1)}
          disabled={clamped >= totalPages}
          aria-label="下一页"
        >
          ›
        </button>
      </div>
    </nav>
  )
}
