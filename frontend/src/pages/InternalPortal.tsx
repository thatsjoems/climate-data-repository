import { useEffect, useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import apiClient from '../api/client'
import { useAuth } from '../context/AuthContext'
import PortalShell, { SidebarItem, PlatformStatus } from '../components/PortalShell'

interface KPI {
  total_institutions: number
  total_submissions: number
  valid_submissions: number
  invalid_submissions: number
  pending_submissions: number
  approved_submissions: number
  rejected_submissions: number
  total_loan_exposure_tzs: number
  total_collateral_value_tzs: number
}

interface Submission {
  id: string
  institution_id: string
  file_name: string
  reporting_period: string
  status: string
  total_records: number
  valid_records: number
  invalid_records: number
  created_at: string
}

interface HazardExposure {
  region: string
  hazard_type: string | null
  exposed_loan_amount_tzs: number
  record_count: number
}

interface CombinedExposure {
  region: string
  reporting_period: string
  avg_rainfall_mm: number | null
  avg_temperature_c: number | null
  hazard_types_recorded: string[]
  total_loan_exposure_tzs: number
  total_collateral_value_tzs: number
  record_count: number
}

interface RiskAdvisory {
  id: string
  title: string
  region: string | null
  hazard_type: string | null
  risk_level: string
  narrative: string
  recommendation: string | null
  data_snapshot: string | null
  created_by_user_id: string
  created_at: string
}

interface SimpleUser {
  id: string
  full_name: string
}

function formatTZS(n: number) {
  return new Intl.NumberFormat('en-TZ', { maximumFractionDigits: 0 }).format(n) + ' TZS'
}

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const PIE_COLORS = ['#12395B', '#0FA47F', '#E28413', '#C0362C', '#7F77DD', '#94A3B8']

function buildConicGradient(segments: { label: string; value: number; color: string }[]) {
  const total = segments.reduce((sum, s) => sum + s.value, 0)
  if (total === 0) return { css: '#EDEBE3', legend: segments.map((s) => ({ ...s, pct: 0 })) }
  let acc = 0
  const stops: string[] = []
  const legend = segments.map((s) => {
    const pct = (s.value / total) * 100
    const start = acc
    const end = acc + pct
    stops.push(`${s.color} ${start}% ${end}%`)
    acc = end
    return { ...s, pct: Math.round(pct) }
  })
  return { css: `conic-gradient(${stops.join(', ')})`, legend }
}

function PieChart({ segments }: { segments: { label: string; value: number; color: string }[] }) {
  const { css, legend } = buildConicGradient(segments)
  return (
    <div className="pie-chart-row">
      <div className="pie-chart" style={{ background: css }} />
      <div className="pie-legend">
        {legend.map((s) => (
          <div className="pie-legend-item" key={s.label}>
            <span className="pie-legend-swatch" style={{ background: s.color }} />
            <span>{s.label} — {s.pct}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function InternalPortal() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [kpi, setKpi] = useState<KPI | null>(null)
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [hazardExposure, setHazardExposure] = useState<HazardExposure[]>([])
  const [combinedExposure, setCombinedExposure] = useState<CombinedExposure[]>([])
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [notesById, setNotesById] = useState<Record<string, string>>({})
  const [showExportNotice, setShowExportNotice] = useState(false)
  const [riskAdvisories, setRiskAdvisories] = useState<RiskAdvisory[]>([])
  const [userMap, setUserMap] = useState<Record<string, string>>({})
  const [expandedNoteId, setExpandedNoteId] = useState<string | null>(null)
  const [advisoryForm, setAdvisoryForm] = useState({
    title: '', region: '', hazard_type: '', risk_level: 'MEDIUM', narrative: '', recommendation: '',
  })
  const [advisoryMessage, setAdvisoryMessage] = useState<string | null>(null)
  const [submittingAdvisory, setSubmittingAdvisory] = useState(false)

  async function loadAll() {
    const [kpiRes, subsRes, hazardRes, combinedRes, advisoryRes, usersRes] = await Promise.all([
      apiClient.get('/analytics/kpi-summary'),
      apiClient.get('/submissions'),
      apiClient.get('/analytics/hazard-exposure'),
      apiClient.get('/analytics/combined-climate-financial-exposure'),
      apiClient.get('/risk-advisories'),
      apiClient.get('/users'),
    ])
    setKpi(kpiRes.data)
    setSubmissions(subsRes.data)
    setHazardExposure(hazardRes.data)
    setCombinedExposure(combinedRes.data)
    setRiskAdvisories(advisoryRes.data)
    const map: Record<string, string> = {}
    ;(usersRes.data as SimpleUser[]).forEach((u) => { map[u.id] = u.full_name })
    setUserMap(map)
  }

  async function handleCreateAdvisory(e: FormEvent) {
    e.preventDefault()
    setAdvisoryMessage(null)
    setSubmittingAdvisory(true)
    try {
      await apiClient.post('/risk-advisories', {
        ...advisoryForm,
        region: advisoryForm.region || null,
        hazard_type: advisoryForm.hazard_type || null,
        recommendation: advisoryForm.recommendation || null,
      })
      setAdvisoryForm({ title: '', region: '', hazard_type: '', risk_level: 'MEDIUM', narrative: '', recommendation: '' })
      setAdvisoryMessage('Risk advisory published.')
      loadAll()
    } catch (err: any) {
      setAdvisoryMessage(err?.response?.data?.detail || 'Failed to publish the advisory.')
    } finally {
      setSubmittingAdvisory(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  async function handleReview(submissionId: string, decision: 'APPROVE' | 'REJECT') {
    await apiClient.post(`/submissions/${submissionId}/review`, {
      decision,
      notes: notesById[submissionId] || '',
    })
    loadAll()
  }

  const filteredSubmissions =
    statusFilter === 'ALL' ? submissions : submissions.filter((s) => s.status === statusFilter)

  const statusSegments = kpi ? [
    { label: 'Pending', value: kpi.pending_submissions, color: '#94A3B8' },
    { label: 'Valid', value: kpi.valid_submissions, color: '#0FA47F' },
    { label: 'Invalid', value: kpi.invalid_submissions, color: '#C0362C' },
    { label: 'Approved', value: kpi.approved_submissions, color: '#12395B' },
    { label: 'Rejected', value: kpi.rejected_submissions, color: '#7F2C2C' },
  ] : []

  const hazardTotals: Record<string, number> = {}
  hazardExposure.forEach((h) => {
    const key = h.hazard_type || 'None'
    hazardTotals[key] = (hazardTotals[key] || 0) + h.exposed_loan_amount_tzs
  })
  const hazardSegments = Object.entries(hazardTotals).map(([label, value], i) => ({
    label, value, color: PIE_COLORS[i % PIE_COLORS.length],
  }))

  const platforms: PlatformStatus[] = [
    { name: 'ArcGIS', connected: false },
    { name: 'QGIS', connected: false },
    { name: 'BSIS', connected: false },
    { name: 'RTIS', connected: false },
  ]

  const sidebarItems: SidebarItem[] = [
    { key: 'overview', icon: '📊', label: 'Overview', active: true, onClick: () => scrollTo('top-anchor') },
    { key: 'loan', icon: '💰', label: 'Loan Data', onClick: () => scrollTo('kpi-section') },
    { key: 'collateral', icon: '🛡️', label: 'Collateral Data', onClick: () => scrollTo('kpi-section') },
    { key: 'climate', icon: '🌦️', label: 'Climate & Hazard Data', onClick: () => scrollTo('hazard-section') },
    { key: 'combined', icon: '🔗', label: 'Combined Climate-Financial', onClick: () => scrollTo('combined-section') },
    { key: 'risk', icon: '🧭', label: 'Risk Advisory Reports', onClick: () => scrollTo('risk-advisory-section') },
    { key: 'submissions', icon: '📄', label: 'Submission Status', onClick: () => scrollTo('monitoring-section') },
    { key: 'map', icon: '🗺️', label: 'Geospatial Map', onClick: () => scrollTo('map-section') },
    { key: 'export', icon: '⬇️', label: 'Download / Export', onClick: () => setShowExportNotice(true) },
    ...(user?.role === 'SYSTEM_ADMIN'
      ? [{ key: 'admin', icon: '⚙️', label: 'Administration', onClick: () => navigate('/admin') } as SidebarItem]
      : []),
  ]

  return (
    <PortalShell
      theme="bot"
      brandTitle="Climate Data Repository"
      brandSubtitle="Bank of Tanzania"
      pageTitle="Climate Data Repository"
      pageSubtitle="Reliable climate data. Informed decisions. Resilient financial sector."
      items={sidebarItems}
      platforms={platforms}
    >
      <div id="top-anchor" />

      {showExportNotice && (
        <div className="alert-info">
          Export functionality (PDF / Excel / CSV) is planned for a future release — see the
          Requirements Traceability Matrix.
          <button style={{ marginLeft: '0.75rem' }} onClick={() => setShowExportNotice(false)}>Dismiss</button>
        </div>
      )}

      {kpi && (
        <section className="kpi-grid-v2" id="kpi-section">
          <div className="kpi-card-v2">
            <div className="kpi-icon-box" style={{ background: '#FDF0DC' }}>💰</div>
            <div className="kpi-card-v2-text">
              <span className="kpi-label">Total Loan Value</span>
              <span className="kpi-number">{formatTZS(kpi.total_loan_exposure_tzs)}</span>
            </div>
          </div>
          <div className="kpi-card-v2">
            <div className="kpi-icon-box" style={{ background: '#E6F1FB' }}>🛡️</div>
            <div className="kpi-card-v2-text">
              <span className="kpi-label">Total Collateral Value</span>
              <span className="kpi-number">{formatTZS(kpi.total_collateral_value_tzs)}</span>
            </div>
          </div>
          <div className="kpi-card-v2">
            <div className="kpi-icon-box" style={{ background: '#EAF3DE' }}>🏦</div>
            <div className="kpi-card-v2-text">
              <span className="kpi-label">Reporting Institutions</span>
              <span className="kpi-number">{kpi.total_institutions}</span>
            </div>
          </div>
          <div className="kpi-card-v2">
            <div className="kpi-icon-box" style={{ background: '#FAECE7' }}>📄</div>
            <div className="kpi-card-v2-text">
              <span className="kpi-label">Total Submissions</span>
              <span className="kpi-number">{kpi.total_submissions}</span>
            </div>
          </div>
        </section>
      )}

      <section className="card" id="map-section">
        <h2>🗺️ Geospatial Overview — Hazard Exposure & Portfolio</h2>
        <div className="placeholder-panel">
          <span className="placeholder-icon">🗺️</span>
          <strong>Geospatial visualization requires QGIS / ArcGIS integration</strong>
          <span>Not available in this training environment — see Assumptions &amp; Limitations. The tabular hazard exposure below uses real submission data.</span>
        </div>
      </section>

      <section className="card" id="hazard-section">
        <h2>🌦️ Climate Hazard Exposure Distribution</h2>
        <p className="note">Share of valid loan exposure associated with each reported climate hazard.</p>
        <PieChart segments={hazardSegments.length ? hazardSegments : [{ label: 'No data yet', value: 1, color: '#EDEBE3' }]} />
      </section>

      <section className="card">
        <h2>📊 Submission Status Distribution</h2>
        <PieChart segments={statusSegments.length ? statusSegments : [{ label: 'No data yet', value: 1, color: '#EDEBE3' }]} />
      </section>

      <section className="card" id="combined-section">
        <h2>🔗 Combined Climate-Financial Exposure</h2>
        <p className="note">
          Real meteorological readings (rainfall, temperature, recorded hazards) joined with
          real loan/collateral exposure for the same region and reporting period — this is
          what directly links climate data to financial stability, rather than the two
          datasets sitting in separate, unrelated tables. A blank climate column means no
          meteorological reading exists for that region/period — it is never guessed or filled in.
        </p>
        <table>
          <thead>
            <tr>
              <th>Region</th><th>Period</th><th>Avg Rainfall</th><th>Avg Temp</th>
              <th>Hazards Recorded</th><th>Loan Exposure</th><th>Collateral</th><th>Records</th>
            </tr>
          </thead>
          <tbody>
            {combinedExposure.map((c, idx) => (
              <tr key={idx}>
                <td>{c.region}</td>
                <td>{c.reporting_period}</td>
                <td>{c.avg_rainfall_mm !== null ? `${c.avg_rainfall_mm} mm` : '—'}</td>
                <td>{c.avg_temperature_c !== null ? `${c.avg_temperature_c} °C` : '—'}</td>
                <td>{c.hazard_types_recorded.length ? c.hazard_types_recorded.join(', ') : '—'}</td>
                <td>{formatTZS(c.total_loan_exposure_tzs)}</td>
                <td>{formatTZS(c.total_collateral_value_tzs)}</td>
                <td>{c.record_count}</td>
              </tr>
            ))}
            {combinedExposure.length === 0 && <tr><td colSpan={8}>No matching data yet.</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="card" id="risk-advisory-section">
        <h2>🧭 Risk Advisory Reports</h2>
        <p className="note">
          Analyst-authored climate risk assessments for internal BOT decision-making —
          e.g. "elevated flood exposure in Region X suggests caution on new large loans
          in that area." The risk level and recommendation are the analyst's own
          professional judgement; the figures shown are always real, queried data,
          never invented.
        </p>

        {user?.role === 'BOT_USER' && (
          <form onSubmit={handleCreateAdvisory} className="upload-form" style={{ maxWidth: 560, marginBottom: '1.25rem' }}>
            <label>Title</label>
            <input
              required
              value={advisoryForm.title}
              onChange={(e) => setAdvisoryForm({ ...advisoryForm, title: e.target.value })}
              placeholder="e.g. Elevated flood exposure — Morogoro"
            />
            <label>Region (optional — leave blank for a cross-region note)</label>
            <input
              value={advisoryForm.region}
              onChange={(e) => setAdvisoryForm({ ...advisoryForm, region: e.target.value })}
              placeholder="e.g. Morogoro"
              list="region-options"
            />
            <datalist id="region-options">
              {[...new Set(hazardExposure.map((h) => h.region))].map((r) => <option key={r} value={r} />)}
            </datalist>
            <label>Hazard Type (optional)</label>
            <select
              value={advisoryForm.hazard_type}
              onChange={(e) => setAdvisoryForm({ ...advisoryForm, hazard_type: e.target.value })}
            >
              <option value="">-- Any / Not specific --</option>
              <option value="Drought">Drought</option>
              <option value="Flood">Flood</option>
              <option value="Cyclone">Cyclone</option>
              <option value="Landslide">Landslide</option>
            </select>
            <label>Risk Level (your assessment)</label>
            <select
              value={advisoryForm.risk_level}
              onChange={(e) => setAdvisoryForm({ ...advisoryForm, risk_level: e.target.value })}
            >
              <option value="LOW">Low</option>
              <option value="MEDIUM">Medium</option>
              <option value="HIGH">High</option>
              <option value="CRITICAL">Critical</option>
            </select>
            <label>Narrative / Analysis</label>
            <textarea
              required
              rows={4}
              value={advisoryForm.narrative}
              onChange={(e) => setAdvisoryForm({ ...advisoryForm, narrative: e.target.value })}
              placeholder="What does the data show, and why does it matter?"
              style={{ padding: '0.6rem', borderRadius: 8, border: '1px solid var(--color-border)', fontFamily: 'inherit', fontSize: '0.88rem' }}
            />
            <label>Recommendation to BOT decision-makers (optional)</label>
            <textarea
              rows={3}
              value={advisoryForm.recommendation}
              onChange={(e) => setAdvisoryForm({ ...advisoryForm, recommendation: e.target.value })}
              placeholder="e.g. Recommend enhanced due diligence on new large loans in this region."
              style={{ padding: '0.6rem', borderRadius: 8, border: '1px solid var(--color-border)', fontFamily: 'inherit', fontSize: '0.88rem' }}
            />
            <button className="btn-accent" type="submit" disabled={submittingAdvisory}>
              {submittingAdvisory ? 'Publishing...' : 'Publish Advisory'}
            </button>
            {advisoryMessage && <div className="alert-info">{advisoryMessage}</div>}
          </form>
        )}

        <div className="advisory-list">
          {riskAdvisories.map((note) => {
            let snapshot: any = null
            try { snapshot = note.data_snapshot ? JSON.parse(note.data_snapshot) : null } catch { /* ignore */ }
            const expanded = expandedNoteId === note.id
            return (
              <div className="advisory-item" key={note.id} onClick={() => setExpandedNoteId(expanded ? null : note.id)}>
                <div className="advisory-item-head">
                  <div>
                    <h4>{note.title}</h4>
                    <div className="advisory-meta">
                      {note.region || 'All regions'} · {note.hazard_type || 'General'} · by {userMap[note.created_by_user_id] || 'Analyst'} · {new Date(note.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <span className={`badge badge-${note.risk_level.toLowerCase()}`}>{note.risk_level}</span>
                </div>
                {expanded && (
                  <div className="advisory-detail">
                    <h5>Narrative</h5>
                    <p>{note.narrative}</p>
                    {note.recommendation && (<><h5>Recommendation</h5><p>{note.recommendation}</p></>)}
                    {snapshot && (
                      <>
                        <h5>Data Snapshot (at time of writing)</h5>
                        <div className="advisory-snapshot">
                          Loan Exposure: {formatTZS(snapshot.total_loan_exposure_tzs || 0)} ·
                          {' '}Collateral: {formatTZS(snapshot.total_collateral_value_tzs || 0)} ·
                          {' '}Records: {snapshot.matching_record_count ?? 0}
                          {snapshot.latest_climate_reading && (
                            <>
                              <br />
                              Latest Climate Reading ({snapshot.latest_climate_reading.year}-{String(snapshot.latest_climate_reading.month).padStart(2, '0')}):
                              {' '}{snapshot.latest_climate_reading.rainfall_mm} mm rainfall,
                              {' '}{snapshot.latest_climate_reading.avg_temperature_c}°C,
                              {' '}hazard: {snapshot.latest_climate_reading.hazard_type || 'None'}
                              {' '}({snapshot.latest_climate_reading.source})
                            </>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            )
          })}
          {riskAdvisories.length === 0 && <p className="note">No risk advisory reports have been published yet.</p>}
        </div>
      </section>

      <section className="card" id="monitoring-section">
        <h2>📄 Submission Monitoring</h2>
        <label>Filter by Status: </label>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="ALL">All</option>
          <option value="PENDING">Pending</option>
          <option value="VALID">Valid</option>
          <option value="INVALID">Invalid</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
        </select>

        <table>
          <thead>
            <tr>
              <th>File</th><th>Period</th><th>Status</th><th>Valid/Total</th><th>Date</th>
              {(user?.role === 'BOT_USER' || user?.role === 'SYSTEM_ADMIN') && <th>Notes + Decision</th>}
            </tr>
          </thead>
          <tbody>
            {filteredSubmissions.map((s) => (
              <tr key={s.id}>
                <td>{s.file_name}</td>
                <td>{s.reporting_period}</td>
                <td><span className={`badge badge-${s.status.toLowerCase()}`}>{s.status}</span></td>
                <td>{s.valid_records}/{s.total_records}</td>
                <td>{new Date(s.created_at).toLocaleDateString()}</td>
                {(user?.role === 'BOT_USER' || user?.role === 'SYSTEM_ADMIN') && (
                  <td>
                    <input
                      type="text"
                      placeholder="Notes (optional)"
                      value={notesById[s.id] || ''}
                      onChange={(e) => setNotesById({ ...notesById, [s.id]: e.target.value })}
                    />
                    <button onClick={() => handleReview(s.id, 'APPROVE')}>Approve</button>
                    <button onClick={() => handleReview(s.id, 'REJECT')}>Reject</button>
                  </td>
                )}
              </tr>
            ))}
            {filteredSubmissions.length === 0 && (
              <tr><td colSpan={6}>No submissions match this filter.</td></tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2>🌍 Climate & Financial Exposure by Region</h2>
        <p className="note">Total value of loans (from valid submissions) per region and reported climate hazard.</p>
        <table>
          <thead><tr><th>Region</th><th>Hazard</th><th>Loan Exposure</th><th>Record Count</th></tr></thead>
          <tbody>
            {hazardExposure.map((h, idx) => (
              <tr key={idx}>
                <td>{h.region}</td>
                <td>{h.hazard_type || 'None'}</td>
                <td>{formatTZS(h.exposed_loan_amount_tzs)}</td>
                <td>{h.record_count}</td>
              </tr>
            ))}
            {hazardExposure.length === 0 && <tr><td colSpan={4}>No data yet.</td></tr>}
          </tbody>
        </table>
      </section>
    </PortalShell>
  )
}
