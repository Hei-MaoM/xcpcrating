import { useState } from 'react'

interface PaginationProps {
  page: number // 1-based
  pageSize: number
  totalItems: number
  onPageChange: (page: number) => void
}

/** Compact pager with previous/next controls and direct page input. */
export function Pagination({
  page,
  pageSize,
  totalItems,
  onPageChange,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize))
  const [draft, setDraft] = useState<string | null>(null)
  if (totalPages <= 1) return null

  const clamped = Math.min(Math.max(1, page), totalPages)
  const from = (clamped - 1) * pageSize + 1
  const to = Math.min(clamped * pageSize, totalItems)
  function commit() {
    if (draft === null || draft === '') {
      setDraft(null)
      return
    }
    const next = Math.min(totalPages, Math.max(1, Number(draft)))
    if (Number.isFinite(next)) onPageChange(next)
    setDraft(null)
  }

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
        <label className="pagination__jump">
          <span>跳转至</span>
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={totalPages}
            value={draft ?? clamped}
            aria-label={`输入页码，共 ${totalPages} 页`}
            onChange={(event) => setDraft(event.target.value.replace(/\D/g, ''))}
            onBlur={commit}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                commit()
                event.currentTarget.blur()
              }
              if (event.key === 'Escape') {
                setDraft(null)
                event.currentTarget.blur()
              }
            }}
          />
          <span>/ {totalPages}</span>
        </label>
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
