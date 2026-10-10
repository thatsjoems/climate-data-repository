import { useEffect, useState } from 'react'
import apiClient from '../api/client'

/**
 * "Climate Data - Hazard Summary" of the dashboard (Concept Note, Figure 3): for one hazard, the districts where it was
 * recorded and how severe. Everything comes from GET /analytics/hazard-summary, which counts recorded climate readings
 * only: a district without a reading of the hazard is not listed (that is not the same as "no hazard"), and nothing is
 * estimated. It has its own choices (hazard, period, region) because it describes the climate, not the loan portfolio.
 */

export interface HazardSummaryDistrict {
  region: string
  district: string
  readings: number
  highest_severity: string | null
}

export interface HazardSummaryData {
  hazard_type: string
  reporting_period: string | null
  region: string | null
  validated_only: boolean
  districts_affected: number
  regions_affected: number
  readings: number
  readings_without_district: number
  highest_severity: string | null
  districts_by_severity: Record<string, number>
  districts: HazardSummaryDistrict[]
  available_periods: string[]
  available_regions: string[]
}

export const SUMMARY_HAZARDS = ['Drought', 'Flood', 'Landslide', 'Cyclone']
const ROWS_SHOWN = 10

const SEVERITY_LABEL: Record<string, string> = { HIGH: 'High', MEDIUM: 'Medium', LOW: 'Low', NOT_GRADED: 'Not graded' }
const SEVERITY_COLOR: Record<string, string> = { HIGH: '#B91C1C', MEDIUM: '#E07A5F', LOW: '#E8B84A', NOT_GRADED: '#94A3B8' }
const SEVERITY_ORDER = ['HIGH', 'MEDIUM', 'LOW', 'NOT_GRADED']

function severityKey(s: string | null): string {
  return s && SEVERITY_LABEL[s] ? s : 'NOT_GRADED'
}

function SeverityBadge({ severity }: { severity: string | null }) {
  const key = severityKey(severity)
  return (
    <span className="pie-legend-item" style={{ display: 'inline-flex' }}>
      <span className="pie-legend-swatch" style={{ background: SEVERITY_COLOR[key] }} />
      <span>{SEVERITY_LABEL[key]}</span>
    </span>
  )
}

function unique(values: string[], keep: string): string[] {
  return [...new Set(keep ? [...values, keep] : values)]
}

export default function HazardSummary() {
  const [hazard, setHazard] = useState('Drought')
  const [period, setPeriod] = useState('')
  const [region, setRegion] = useState('')
  const [includeUnvalidated, setIncludeUnvalidated] = useState(false)
  const [data, setData] = useState<HazardSummaryData | null>(null)
  const [failed, setFailed] = useState(false)
  const [showAll, setShowAll] = useState(false)
  // The pickers keep the last list they were given, so they do not empty while a new answer is loading.
  const [periods, setPeriods] = useState<string[]>([])
  const [regions, setRegions] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    setFailed(false)
    const params = new URLSearchParams({ filter_hazard_type: hazard })
    if (period) params.set('filter_reporting_period', period)
    if (region) params.set('filter_region', region)
    if (includeUnvalidated) params.set('validated_only', 'false')
    apiClient
      .get(`/analytics/hazard-summary?${params.toString()}`)
      .then((res) => {
        if (cancelled) return
        setData(res.data)
        setPeriods(res.data.available_periods || [])
        setRegions(res.data.available_regions || [])
        setShowAll(false)
      })
      .catch(() => { if (!cancelled) { setData(null); setFailed(true) } })
    return () => { cancelled = true }
  }, [hazard, period, region, includeUnvalidated])

  const shown = data ? (showAll ? data.districts : data.districts.slice(0, ROWS_SHOWN)) : []
  const maxDistricts = data ? Math.max(...SEVERITY_ORDER.map((k) => data.districts_by_severity[k] || 0), 1) : 1

  return (
    <section className="card" id="hazard-summary-section">
      <h2>🌡️ Climate Data — Hazard Summary</h2>
      <p className="note" style={{ marginTop: 0 }}>
        Recorded climate readings only. A district that is not listed has no reading of this hazard in the selection:
        that does not mean it is safe. Readings that are flagged are never counted.
      </p>

      <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: '0.8rem' }}>
        <div>
          <label htmlFor="hs-hazard" style={{ display: 'block', fontSize: '0.78rem', marginBottom: '0.2rem' }}>Hazard type</label>
          <select id="hs-hazard" value={hazard} onChange={(e) => setHazard(e.target.value)}>
            {SUMMARY_HAZARDS.map((h) => <option key={h} value={h}>{h}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="hs-period" style={{ display: 'block', fontSize: '0.78rem', marginBottom: '0.2rem' }}>Time period</label>
          <select id="hs-period" value={period} onChange={(e) => setPeriod(e.target.value)}>
            <option value="">All periods</option>
            {unique(periods, period).map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="hs-region" style={{ display: 'block', fontSize: '0.78rem', marginBottom: '0.2rem' }}>Region</label>
          <select id="hs-region" value={region} onChange={(e) => setRegion(e.target.value)}>
            <option value="">All regions</option>
            {unique(regions, region).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <label style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', fontSize: '0.8rem' }}>
          <input type="checkbox" checked={includeUnvalidated} onChange={(e) => setIncludeUnvalidated(e.target.checked)} />
          Include readings not yet validated
        </label>
      </div>

      {failed && <p className="alert-warning">The hazard summary could not be loaded.</p>}
      {!failed && data === null && <p style={{ fontSize: '0.82rem' }}>Loading…</p>}

      {data !== null && data.readings === 0 && (
        <p style={{ fontSize: '0.85rem' }}>
          No {data.hazard_type} readings are recorded for this selection
          {data.validated_only ? ' (validated readings only; tick the box above to include those not yet validated)' : ''}.
        </p>
      )}

      {data !== null && data.readings > 0 && (
        <>
          <div className="portfolio-grid" style={{ marginBottom: '1rem' }}>
            <div className="portfolio-panel">
              <h3>Districts with {data.hazard_type} recorded</h3>
              <div style={{ fontSize: '1.7rem', fontWeight: 700 }} data-testid="hs-districts">{data.districts_affected}</div>
            </div>
            <div className="portfolio-panel">
              <h3>Regions</h3>
              <div style={{ fontSize: '1.7rem', fontWeight: 700 }} data-testid="hs-regions">{data.regions_affected}</div>
            </div>
            <div className="portfolio-panel">
              <h3>Highest severity recorded</h3>
              <div style={{ fontSize: '1.2rem', fontWeight: 700 }} data-testid="hs-highest">
                {data.highest_severity ? SEVERITY_LABEL[severityKey(data.highest_severity)] : 'Not graded'}
              </div>
            </div>
            <div className="portfolio-panel">
              <h3>Readings counted</h3>
              <div style={{ fontSize: '1.7rem', fontWeight: 700 }} data-testid="hs-readings">{data.readings}</div>
            </div>
          </div>

          <div className="portfolio-grid">
            <div className="portfolio-panel">
              <h3>Districts by highest severity</h3>
              <div className="hbar-list">
                {SEVERITY_ORDER.map((k) => {
                  const n = data.districts_by_severity[k] || 0
                  return (
                    <div className="hbar-row" key={k}>
                      <span className="hbar-label">{SEVERITY_LABEL[k]}</span>
                      <span className="hbar-track">
                        <span className="hbar-fill" style={{ width: `${(100 * n) / maxDistricts}%`, background: SEVERITY_COLOR[k] }} />
                      </span>
                      <span className="hbar-value">{n}</span>
                    </div>
                  )
                })}
              </div>
            </div>

            <div className="portfolio-panel" style={{ gridColumn: 'span 2' }}>
              <h3>Districts, worst first</h3>
              {data.districts.length === 0 ? (
                <p style={{ fontSize: '0.82rem', margin: 0 }}>No reading names a district; see the note below.</p>
              ) : (
                <>
                  <table style={{ marginTop: 0 }}>
                    <thead>
                      <tr><th>District</th><th>Region</th><th>Readings</th><th>Highest severity</th></tr>
                    </thead>
                    <tbody>
                      {shown.map((d) => (
                        <tr key={`${d.region}/${d.district}`}>
                          <td>{d.district}</td>
                          <td>{d.region}</td>
                          <td>{d.readings}</td>
                          <td><SeverityBadge severity={d.highest_severity} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {data.districts.length > ROWS_SHOWN && (
                    <button type="button" className="link-button" style={{ marginTop: '0.5rem' }} onClick={() => setShowAll(!showAll)}>
                      {showAll ? `Show the worst ${ROWS_SHOWN} only` : `Show all ${data.districts.length} districts`}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          {data.readings_without_district > 0 && (
            <p className="note">
              {data.readings_without_district} of these readings were recorded for a region only, so they are counted above
              but cannot be placed in a district.
            </p>
          )}
        </>
      )}

      <p className="note" style={{ marginBottom: 0 }}>
        The number of people affected is not shown: the repository holds no population figures, and none is estimated.
        Severity is the grade given with each reading (Low, Medium or High); a reading without a grade is shown as "Not graded".
      </p>
    </section>
  )
}
