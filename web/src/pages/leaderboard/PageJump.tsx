import { useState } from 'react'

interface PageJumpProps {
  page: number
  totalPages: number
  disabled?: boolean
  onChange: (page: number) => void
}

export function PageJump({ page, totalPages, disabled, onChange }: PageJumpProps) {
  const [draft, setDraft] = useState<string | null>(null)

  function commit() {
    if (draft === null || draft === '') {
      setDraft(null)
      return
    }
    const next = Math.min(totalPages, Math.max(1, Number(draft)))
    if (Number.isFinite(next)) onChange(next)
    setDraft(null)
  }

  return (
    <label className="pager__jump">
      <span>跳转至</span>
      <input
        type="number"
        inputMode="numeric"
        min={1}
        max={totalPages}
        value={draft ?? page}
        disabled={disabled}
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
  )
}
