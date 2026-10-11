/** The three severity grades a climate reading can carry, how they are named and coloured, shared by the Hazard Summary's table, bars and map. */
export const SEVERITY_LABEL: Record<string, string> = { HIGH: 'High', MEDIUM: 'Medium', LOW: 'Low', NOT_GRADED: 'Not graded' }
export const SEVERITY_COLOR: Record<string, string> = { HIGH: '#B91C1C', MEDIUM: '#E07A5F', LOW: '#E8B84A', NOT_GRADED: '#94A3B8' }
export const SEVERITY_ORDER = ['HIGH', 'MEDIUM', 'LOW', 'NOT_GRADED']
/** A district on the map with no reading of the chosen hazard in the selection (not the same as "no hazard"). */
export const NO_READING_COLOR = '#E2E8F0'

export function severityKey(s: string | null): string {
  return s && SEVERITY_LABEL[s] ? s : 'NOT_GRADED'
}
