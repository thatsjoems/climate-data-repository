import { useEffect, useState } from 'react'
import apiClient from '../api/client'

/**
 * Portfolio charts of the dashboard (Concept Note, Figure 3): borrower type, currency, loan type,
 * loan by sector / region / bank, collateral by type / sector / region, and a drill-down
 * region -> district -> ward. Every figure comes from GET /analytics/portfolio-breakdown, which
 * counts the same approved, current rows as the Summary Figures, so the charts cannot disagree with them.
 */

export interface BreakdownItem {
  label: string
  value: number
  record_count: number
  share_pct: number
}

type Metric = 'loan' | 'outstanding' | 'collateral' | 'records' | 'borrowers'

const PALETTE = ['#2B353A', '#C99A2E', '#3B82A0', '#10B981', '#E07A5F', '#8B5CF6', '#94A3B8']

/** 55,660,000,000,000 -> "55.66 T", 8,420,000,000 -> "8.42 B": the compact form the mockup uses. */
export function compactNumber(n: number): string {
  const abs = Math.abs(n)
  if (abs >= 1e12) return (n / 1e12).toFixed(2) + ' T'
  if (abs >= 1e9) return (n / 1e9).toFixed(2) + ' B'
  if (abs >= 1e6) return (n / 1e6).toFixed(2) + ' M'
  if (abs >= 1e3) return (n / 1e3).toFixed(1) + ' K'
  return String(Math.round(n))
}

function formatValue(n: number, metric: Metric): string {
  return metric === 'records' || metric === 'borrowers' ? Math.round(n).toLocaleString('en-US') : compactNumber(n)
}

function colorFor(index: number, label: string): string {
  return label === 'Others' || label === 'Unspecified' ? '#CBD5E1' : PALETTE[index % PALETTE.length]
}

function Donut({ items, metric }: { items: BreakdownItem[]; metric: Metric }) {
  let acc = 0
  const stops = items.map((it, i) => {
    const start = acc
    acc += it.share_pct
    return `${colorFor(i, it.label)} ${start}% ${acc}%`
  })
  const css = items.length ? `conic-gradient(${stops.join(', ')})` : '#EDEBE3'
  return (
    <div className="pie-chart-row">
      <div className="donut-chart" style={{ background: css }} role="img" aria-label="Share by group" />
      <div className="pie-legend">
        {items.map((it, i) => (
          <div className="pie-legend-item" key={it.label}>
            <span className="pie-legend-swatch" style={{ background: colorFor(i, it.label) }} />
            <span>{it.label} — {it.share_pct}% ({formatValue(it.value, metric)})</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function Bars({ items, metric, onSelect }: { items: BreakdownItem[]; metric: Metric; onSelect?: (label: string) => void }) {
  const max = Math.max(...items.map((i) => i.value), 1)
  return (
    <div className="hbar-list">
      {items.map((it, i) => {
        const clickable = !!onSelect && it.label !== 'Others' && it.label !== 'Unspecified'
        return (
          <div
            className={`hbar-row${clickable ? ' is-clickable' : ''}`}
            key={it.label}
            onClick={clickable ? () => onSelect!(it.label) : undefined}
            title={clickable ? `Drill down into ${it.label}` : undefined}
          >
            <span className="hbar-label">{it.label}</span>
            <span className="hbar-track">
              <span className="hbar-fill" style={{ width: `${(100 * it.value) / max}%`, background: colorFor(i, it.label) }} />
            </span>
            <span className="hbar-value">{formatValue(it.value, metric)}</span>
          </div>
        )
      })}
    </div>
  )
}

function Panel({
  title, groupBy, metric, kind, filterQuery, limit = 6, extraQuery = '', onSelect,
}: {
  title: string
  groupBy: string
  metric: Metric
  kind: 'donut' | 'bars'
  filterQuery: string
  limit?: number
  extraQuery?: string
  onSelect?: (label: string) => void
}) {
  const [items, setItems] = useState<BreakdownItem[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setFailed(false)
    const params = new URLSearchParams(filterQuery)
    for (const [k, v] of new URLSearchParams(extraQuery)) params.set(k, v)
    params.set('group_by', groupBy)
    params.set('metric', metric)
    params.set('limit', String(limit))
    apiClient
      .get(`/analytics/portfolio-breakdown?${params.toString()}`)
      .then((res) => { if (!cancelled) setItems(res.data) })
      .catch(() => { if (!cancelled) { setItems(null); setFailed(true) } })
    return () => { cancelled = true }
  }, [filterQuery, extraQuery, groupBy, metric, limit])

  return (
    <div className="portfolio-panel">
      <h3>{title}</h3>
      {failed && <p className="alert-warning" style={{ margin: 0 }}>This chart could not be loaded.</p>}
      {!failed && items === null && <p style={{ margin: 0, fontSize: '0.8rem' }}>Loading…</p>}
      {items !== null && items.length === 0 && <p style={{ margin: 0, fontSize: '0.8rem' }}>No approved data yet.</p>}
      {items !== null && items.length > 0 && (kind === 'donut'
        ? <Donut items={items} metric={metric} />
        : <Bars items={items} metric={metric} onSelect={onSelect} />)}
    </div>
  )
}

export default function PortfolioCharts({ filterQuery }: { filterQuery: string }) {
  // Drill-down path: [] = regions, [region] = its districts, [region, district] = its wards.
  const [path, setPath] = useState<string[]>([])
  const level = path.length === 0 ? 'region' : path.length === 1 ? 'district' : 'ward'
  const extra = new URLSearchParams()
  if (path[0]) extra.set('filter_region', path[0])
  if (path[1]) extra.set('filter_district', path[1])

  return (
    <section className="card" id="portfolio-section">
      <h2>📊 Loan Structure & Collateral Exposure</h2>
      <p style={{ fontSize: '0.82rem', marginTop: 0 }}>
        Approved submissions only, filtered like the Summary Figures above. Click a region bar to drill down to its districts and wards.
      </p>

      <h3 className="portfolio-heading">Loan structure</h3>
      <div className="portfolio-grid">
        <Panel title="Borrower type" groupBy="borrower_type" metric="loan" kind="donut" filterQuery={filterQuery} />
        <Panel title="Loan by currency" groupBy="currency" metric="loan" kind="donut" filterQuery={filterQuery} />
        <Panel title="Loan type" groupBy="loan_type" metric="loan" kind="donut" filterQuery={filterQuery} />
        <Panel title="Loan by sector (top 6)" groupBy="sector" metric="loan" kind="bars" filterQuery={filterQuery} />
        <Panel title="Loan by bank (top 6)" groupBy="institution" metric="loan" kind="bars" filterQuery={filterQuery} />
        <Panel title="Loan by asset classification" groupBy="asset_classification" metric="loan" kind="donut" filterQuery={filterQuery} />
      </div>

      <h3 className="portfolio-heading">Collateral exposure</h3>
      <div className="portfolio-grid">
        <Panel title="Collateral by type" groupBy="collateral_type" metric="collateral" kind="donut" filterQuery={filterQuery} limit={7} />
        <Panel title="Collateral by sector (top 6)" groupBy="collateral_sector" metric="collateral" kind="bars" filterQuery={filterQuery} />
        <Panel title="Collateral by region (top 6)" groupBy="collateral_region" metric="collateral" kind="bars" filterQuery={filterQuery} />
      </div>

      <h3 className="portfolio-heading">
        Drill-down: loan by {level}
        {path.length > 0 && (
          <span className="portfolio-crumbs">
            <button type="button" className="link-button" onClick={() => setPath([])}>All regions</button>
            {path.map((p, i) => (
              <span key={p}> › <button type="button" className="link-button" onClick={() => setPath(path.slice(0, i + 1))}>{p}</button></span>
            ))}
          </span>
        )}
      </h3>
      <div className="portfolio-grid portfolio-grid-single">
        <Panel
          title={`Loan by ${level} (top 10)`}
          groupBy={level}
          metric="loan"
          kind="bars"
          limit={10}
          filterQuery={filterQuery}
          extraQuery={extra.toString()}
          onSelect={level === 'ward' ? undefined : (label) => setPath([...path, label])}
        />
      </div>
    </section>
  )
}
