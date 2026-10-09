import { useEffect, useRef, useState } from 'react'
import { ALL_OPTION, NONE_OPTION, isChecked, summaryLabel, toggleOption } from '../data/mapLayers'

/**
 * A drop-down list with a tick box in front of each choice, so more than one can be chosen at the same time
 * (for example Flood and Drought together). The list offers "None" and "All" first, then one box per option.
 *
 * Nothing changes on the map while boxes are being ticked: the choice is only used when "Apply" is pressed.
 * Closing the list any other way (a click elsewhere, Escape) leaves the previous choice as it was.
 */
export default function CheckboxDropdown({
  label, options, selected, onApply, swatches,
}: {
  label: string
  options: string[]
  selected: string[]
  onApply: (next: string[]) => void
  swatches?: Record<string, string>   // option -> a CSS colour shown beside it
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<string[]>(selected)
  const rootRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!open) return
    function onMouseDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [open])

  function toggleOpen() {
    if (!open) setDraft(selected)   // always start from what is currently applied
    setOpen(!open)
  }

  function apply() {
    onApply(draft)
    setOpen(false)
  }

  const rows = [NONE_OPTION, ALL_OPTION, ...options]

  return (
    <span
      ref={rootRef}
      className="layer-dropdown"
      onKeyDown={(e) => { if (e.key === 'Escape') setOpen(false) }}
    >
      <button
        type="button"
        className="layer-dropdown-button"
        aria-haspopup="true"
        aria-expanded={open}
        onClick={toggleOpen}
      >
        {label}: {summaryLabel(selected, options)} ▾
      </button>
      {open && (
        <div className="layer-dropdown-panel" role="group" aria-label={`${label} options`}>
          {rows.map((option) => (
            <label key={option} className="layer-dropdown-row">
              <input
                type="checkbox"
                checked={isChecked(draft, option, options)}
                onChange={() => setDraft(toggleOption(draft, option, options))}
              />
              {swatches && swatches[option] && (
                <span className="layer-dropdown-swatch" style={{ background: swatches[option] }} />
              )}
              {option}
            </label>
          ))}
          <button type="button" className="btn-accent btn-sm layer-dropdown-apply" onClick={apply}>Apply</button>
        </div>
      )}
    </span>
  )
}
