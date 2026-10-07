interface PagerBarProps {
  total: number
  offset: number
  pageSize: number
  noun: string
  onChange: (offset: number) => void
}

// "Showing rows 1 to 50 of 15,000" with Previous and Next. Long lists are never drawn in one go:
// a file can hold 100,000 rows, and drawing them all freezes the browser.
export default function PagerBar({ total, offset, pageSize, noun, onChange }: PagerBarProps) {
  if (total <= 0) return null
  const from = offset + 1
  const to = Math.min(offset + pageSize, total)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', margin: '0.4rem 0' }}>
      <span className="note" style={{ margin: 0 }}>
        Showing {noun} {from.toLocaleString()} to {to.toLocaleString()} of {total.toLocaleString()}
      </span>
      {total > pageSize && (
        <>
          <button className="btn-secondary btn-sm" disabled={offset <= 0} onClick={() => onChange(Math.max(0, offset - pageSize))}>Previous</button>
          <button className="btn-secondary btn-sm" disabled={offset + pageSize >= total} onClick={() => onChange(offset + pageSize)}>Next</button>
        </>
      )}
    </div>
  )
}
