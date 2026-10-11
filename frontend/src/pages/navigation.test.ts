import { describe, it, expect } from 'vitest'

// Every entry of a portal's navigation menu must lead somewhere: the page (or a component it shows)
// must carry the id the entry scrolls to. A section without a menu entry is also caught for the
// sections listed below, which a user needs to be able to reach from the menu.
const files = import.meta.glob(['../pages/*.tsx', '../components/*.tsx'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>
const all = Object.values(files).join('\n')

function targets(file: string): string[] {
  // The key's form depends on the tool (`./X.tsx` or `../pages/X.tsx`), so the file is found by its name.
  const found = Object.entries(files).find(([key]) => key.endsWith(`/${file}`))
  if (!found) throw new Error(`${file} was not found among ${Object.keys(files).join(', ')}`)
  const src = found[1]
  return Array.from(src.matchAll(/scrollTo\('([^']+)'\)/g)).map((m) => m[1])
}

describe.each(['InternalPortal.tsx', 'InstitutionPortal.tsx', 'AdminPanel.tsx'])('the menu of %s', (file) => {
  it('only points at sections that exist', () => {
    for (const id of targets(file)) {
      expect(all.includes(`id="${id}"`), `no element has id="${id}"`).toBe(true)
    }
  })
})

describe('sections a user needs are in the menu', () => {
  it('the analyst menu lists the hazard summary, the ingestion and the readings review', () => {
    const t = targets('InternalPortal.tsx')
    for (const id of ['hazard-summary-section', 'ingest-section', 'qc-review-section', 'map-section', 'integration-section']) {
      expect(t).toContain(id)
    }
  })
  it('the administrator menu lists both the forms and the lists', () => {
    const t = targets('AdminPanel.tsx')
    for (const id of ['institutions-card', 'users-card', 'user-list-card', 'institution-list-card', 'audit-card']) {
      expect(t).toContain(id)
    }
  })
})
