import type { ReactNode } from 'react'

export interface Column<Row> {
  /** Stable column id. */
  key: string
  /** Header label. */
  header: ReactNode
  /** Cell renderer. */
  render: (row: Row, index: number) => ReactNode
  /** Right-align + tabular numerals for numeric columns. */
  numeric?: boolean
  /** Center-align (e.g. icons, badges). */
  center?: boolean
  /** Optional fixed width hint. */
  width?: string
  /** Header tooltip. */
  title?: string
}

interface DataTableProps<Row> {
  columns: Column<Row>[]
  rows: Row[]
  /** Stable key extractor. */
  rowKey: (row: Row, index: number) => string
  /** Optional row click handler — makes rows interactive. */
  onRowClick?: (row: Row, index: number) => void
  /** Optional per-row CSS class (e.g. medal tinting). */
  rowClassName?: (row: Row, index: number) => string | undefined
  /** Message shown when there are no rows. */
  emptyMessage?: ReactNode
  /** Accessible caption (visually hidden). */
  caption?: string
}

function cellClass<Row>(col: Column<Row>): string {
  const parts: string[] = []
  if (col.numeric) parts.push('cell--num')
  if (col.center) parts.push('cell--center')
  return parts.join(' ')
}

/**
 * Generic data table. Numeric columns right-align with tabular numerals;
 * rows hover; clickable rows are keyboard-activatable.
 */
export function DataTable<Row>({
  columns,
  rows,
  rowKey,
  onRowClick,
  rowClassName,
  emptyMessage = '暂无数据',
  caption,
}: DataTableProps<Row>) {
  if (rows.length === 0) {
    return (
      <div className="datatable-wrap">
        <table className="datatable tabular">
          {caption ? <caption className="sr-only">{caption}</caption> : null}
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key} className={cellClass(col)} title={col.title}>
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
        </table>
        <p className="datatable__empty">{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div className="datatable-wrap">
      <table className="datatable tabular">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={cellClass(col)}
                style={col.width ? { width: col.width } : undefined}
                title={col.title}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const extra = rowClassName?.(row, index)
            const clickable = Boolean(onRowClick)
            const classes = [
              clickable ? 'is-clickable' : '',
              extra ?? '',
            ]
              .filter(Boolean)
              .join(' ')
            return (
              <tr
                key={rowKey(row, index)}
                className={classes || undefined}
                onClick={clickable ? () => onRowClick?.(row, index) : undefined}
                tabIndex={clickable ? 0 : undefined}
                role={clickable ? 'button' : undefined}
                onKeyDown={
                  clickable
                    ? (event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          onRowClick?.(row, index)
                        }
                      }
                    : undefined
                }
              >
                {columns.map((col) => (
                  <td key={col.key} className={cellClass(col)}>
                    {col.render(row, index)}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
