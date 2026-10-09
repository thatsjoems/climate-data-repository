// Choosing map layers (Geospatial Overview): the rules of the tick-box lists for the Hazard layer and the Financial layer.
//
// Each list shows "None", "All" and then one box per layer. Ticking "All" ticks every layer; ticking "None" clears every layer;
// ticking or unticking one layer changes only that layer, and "All" and "None" follow from what is ticked (All is ticked when every
// layer is, None when nothing is). The result is always listed in the order of `allOptions`, so the same choice is always the same list.

export const NONE_OPTION = 'None'
export const ALL_OPTION = 'All'

export function toggleOption(selected: string[], option: string, allOptions: string[]): string[] {
  if (option === NONE_OPTION) return []
  if (option === ALL_OPTION) return selected.length === allOptions.length ? [] : [...allOptions]
  const next = selected.includes(option) ? selected.filter((s) => s !== option) : [...selected, option]
  return allOptions.filter((o) => next.includes(o))
}

export function isChecked(selected: string[], option: string, allOptions: string[]): boolean {
  if (option === NONE_OPTION) return selected.length === 0
  if (option === ALL_OPTION) return allOptions.length > 0 && allOptions.every((o) => selected.includes(o))
  return selected.includes(option)
}

/** What the closed list shows: "None", "All", or the ticked layers ("Flood, Drought"). */
export function summaryLabel(selected: string[], allOptions: string[]): string {
  if (selected.length === 0) return NONE_OPTION
  if (allOptions.length > 0 && allOptions.every((o) => selected.includes(o))) return ALL_OPTION
  return selected.join(', ')
}

/** Loan exposure per region where `hazard` is the recorded hazard (the figures behind that hazard's surface on the map). */
export function hazardAmountsByRegion(
  rows: { region: string; hazard_type: string | null; exposed_loan_amount_tzs: number }[],
  hazard: string,
): Record<string, number> {
  const amounts: Record<string, number> = {}
  for (const row of rows) {
    if (row.hazard_type === hazard) {
      amounts[row.region] = (amounts[row.region] || 0) + row.exposed_loan_amount_tzs
    }
  }
  return amounts
}
