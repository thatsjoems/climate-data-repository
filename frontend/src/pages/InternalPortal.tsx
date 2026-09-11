import { useEffect, useState, FormEvent } from 'react'
import apiClient from '../api/client'
import { useAuth } from '../context/AuthContext'
import PortalShell, { SidebarItem, PlatformStatus } from '../components/PortalShell'
import HazardMap, { RegionMapPoint } from '../components/HazardMap'

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
  created_by_name: string
  created_at: string
}


function formatTZS(n: number) {
  return new Intl.NumberFormat('en-TZ', { maximumFractionDigits: 0 }).format(n) + ' TZS'
}

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const PIE_COLORS = ['#0A0A0A', '#0FA47F', '#E28413', '#C0362C', '#7F77DD', '#94A3B8']

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

interface DataQuality {
  total_observations: number
  synthetic_observations: number
  validated_observations: number
  unvalidated_observations: number
  flagged_observations: number
  regions_with_data: number
  regions_missing_data: string[]
  latest_ingestion_at: string | null
  total_ingestion_batches: number
  total_records_rejected_all_time: number
  total_records_duplicate_all_time: number
}

interface IngestionBatch {
  id: string
  source: string
  dataset_name: string | null
  file_name: string | null
  records_received: number
  records_accepted: number
  records_rejected: number
  records_duplicate: number
  status: string
  created_at: string
}

export default function InternalPortal() {
  const { user } = useAuth()
  const [kpi, setKpi] = useState<KPI | null>(null)
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [hazardExposure, setHazardExposure] = useState<HazardExposure[]>([])
  const [combinedExposure, setCombinedExposure] = useState<CombinedExposure[]>([])
  const [mapPoints, setMapPoints] = useState<RegionMapPoint[]>([])
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [notesById, setNotesById] = useState<Record<string, string>>({})
  const [reportGenerating, setReportGenerating] = useState(false)
  const [reportMessage, setReportMessage] = useState<string | null>(null)
  const [riskAdvisories, setRiskAdvisories] = useState<RiskAdvisory[]>([])
  const [expandedNoteId, setExpandedNoteId] = useState<string | null>(null)
  const [advisoryForm, setAdvisoryForm] = useState({
    title: '', region: '', hazard_type: '', risk_level: 'MEDIUM', narrative: '', recommendation: '',
  })
  const [advisoryMessage, setAdvisoryMessage] = useState<string | null>(null)
  const [submittingAdvisory, setSubmittingAdvisory] = useState(false)
  const [dataQuality, setDataQuality] = useState<DataQuality | null>(null)
  const [ingestionBatches, setIngestionBatches] = useState<IngestionBatch[]>([])
  const [climateFile, setClimateFile] = useState<File | null>(null)
  const [climateSource, setClimateSource] = useState('MANUAL_UPLOAD')
  const [climateDatasetName, setClimateDatasetName] = useState('')
  const [climateUploading, setClimateUploading] = useState(false)
  const [climateUploadMessage, setClimateUploadMessage] = useState<string | null>(null)

  const [climateQualityError, setClimateQualityError] = useState<string | null>(null)

  async function loadClimateQuality() {
    try {
      const [qRes, batchesRes] = await Promise.all([
        apiClient.get('/climate-data/quality-summary'),
        apiClient.get('/climate-data/ingestions'),
      ])
      setDataQuality(qRes.data)
      setIngestionBatches(batchesRes.data)
      setClimateQualityError(null)
    } catch (err: any) {
      setClimateQualityError(
        err?.response?.status
          ? `Failed to load (HTTP ${err.response.status}): ${err.response.data?.detail || err.message}`
          : `Failed to load: ${err.message}`
      )
    }
  }

  async function handleClimateUpload(e: FormEvent) {
    e.preventDefault()
    if (!climateFile) {
      setClimateUploadMessage('Choose a .csv or .xlsx file first.')
      return
    }
    setClimateUploading(true)
    setClimateUploadMessage(null)
    try {
      const formData = new FormData()
      formData.append('source', climateSource)
      formData.append('dataset_name', climateDatasetName)
      formData.append('file', climateFile)
      const res = await apiClient.post('/climate-data/ingest', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setClimateUploadMessage(
        `Ingested: ${res.data.records_accepted} accepted, ${res.data.records_rejected} rejected, ` +
        `${res.data.records_duplicate} duplicate (of ${res.data.records_received} rows).`
      )
      setClimateFile(null)
      loadClimateQuality()
    } catch (err: any) {
      setClimateUploadMessage(err?.response?.data?.detail || 'Failed to ingest the file.')
    } finally {
      setClimateUploading(false)
    }
  }

  async function loadAll() {
    const [kpiRes, subsRes, hazardRes, combinedRes, advisoryRes, mapRes] = await Promise.all([
      apiClient.get('/analytics/kpi-summary'),
      apiClient.get('/submissions'),
      apiClient.get('/analytics/hazard-exposure'),
      apiClient.get('/analytics/combined-climate-financial-exposure'),
      apiClient.get('/risk-advisories'),
      apiClient.get('/analytics/map-points'),
    ])
    setKpi(kpiRes.data)
    setSubmissions(subsRes.data)
    setHazardExposure(hazardRes.data)
    setCombinedExposure(combinedRes.data)
    setRiskAdvisories(advisoryRes.data)
    setMapPoints(mapRes.data)
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
    loadClimateQuality()
  }, [])

  async function handleGenerateReport() {
    setReportGenerating(true)
    setReportMessage(null)
    try {
      const res = await apiClient.get('/reports/summary.pdf', { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `CDR_Summary_Report_${new Date().toISOString().slice(0, 10)}.pdf`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      setReportMessage('Report generated and downloaded.')
    } catch (err: any) {
      setReportMessage('Failed to generate the report.')
    } finally {
      setReportGenerating(false)
    }
  }

  async function handleDownloadCombinedCsv() {
    const res = await apiClient.get('/reports/combined-exposure.csv', { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `CDR_Combined_Exposure_${new Date().toISOString().slice(0, 10)}.csv`)
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  async function handleGenerateReportExcel() {
    setReportGenerating(true)
    setReportMessage(null)
    try {
      const res = await apiClient.get('/reports/summary.xlsx', { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `CDR_Summary_Report_${new Date().toISOString().slice(0, 10)}.xlsx`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      setReportMessage('Excel report generated and downloaded.')
    } catch (err: any) {
      setReportMessage('Failed to generate the Excel report.')
    } finally {
      setReportGenerating(false)
    }
  }

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
    { label: 'Approved', value: kpi.approved_submissions, color: '#0A0A0A' },
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
    { key: 'quality', icon: '📋', label: 'Climate Data Quality', onClick: () => scrollTo('quality-section') },
    { key: 'combined', icon: '🔗', label: 'Combined Climate-Financial', onClick: () => scrollTo('combined-section') },
    { key: 'risk', icon: '🧭', label: 'Risk Advisory Reports', onClick: () => scrollTo('risk-advisory-section') },
    { key: 'submissions', icon: '📄', label: 'Submission Status', onClick: () => scrollTo('monitoring-section') },
    { key: 'map', icon: '🗺️', label: 'Geospatial Map', onClick: () => scrollTo('map-section') },
    { key: 'export', icon: '⬇️', label: 'Download / Export', onClick: () => scrollTo('reports-section') },
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

      <section className="card" id="reports-section">
        <h2>⬇️ Automated Reports</h2>
        <p className="note">
          Compiles the current KPI summary, climate hazard exposure, combined climate-financial
          exposure, and recent Risk Advisory Reports into a single PDF — the same figures shown
          on this dashboard, ready to file or share instead of copying numbers manually.
        </p>
        <button className="btn-accent" onClick={handleGenerateReport} disabled={reportGenerating}>
          {reportGenerating ? 'Generating...' : 'Generate Summary Report (PDF)'}
        </button>{' '}
        <button onClick={handleGenerateReportExcel} disabled={reportGenerating}>Generate Summary Report (Excel)</button>{' '}
        <button onClick={handleDownloadCombinedCsv}>Download Combined Exposure (CSV)</button>
        {reportMessage && <div className="alert-info">{reportMessage}</div>}
      </section>

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
        <p className="note">
          Region-level view: circle size shows total loan exposure, color shows the dominant reported
          climate hazard for that region. Coordinates are region centroids (not exact loan locations) —
          precise per-loan mapping will follow once BOT's data template includes coordinates. Click a
          circle for details.
        </p>
        {mapPoints.length > 0 ? (
          <HazardMap points={mapPoints} />
        ) : (
          <div className="placeholder-panel">
            <span className="placeholder-icon">🗺️</span>
            <strong>No geolocated exposure data yet</strong>
            <span>Once institutions submit valid data with recognized regions, this map populates automatically.</span>
          </div>
        )}
      </section>

      <section className="card" id="hazard-section">
        <h2>🌦️ Climate Hazard Exposure Distribution</h2>
        <p className="note">Share of valid loan exposure associated with each reported climate hazard.</p>
        <PieChart segments={hazardSegments.length ? hazardSegments : [{ label: 'No data yet', value: 1, color: '#EDEBE3' }]} />
      </section>

      <section className="card" id="quality-section">
        <h2>📋 Climate Data Quality</h2>
        <p className="note">
          Is the climate data complete and trustworthy? Every figure below is a direct count -
          nothing estimated. <strong>SYNTHETIC</strong> observations are demo data only and are
          never presented as official TMA readings.
        </p>
        {climateQualityError && (
          <div className="alert-error">
            ⚠️ {climateQualityError}
            <button style={{ marginLeft: '0.75rem' }} onClick={loadClimateQuality}>Retry</button>
          </div>
        )}
        {dataQuality && (
          <div className="quality-grid">
            <div className="quality-stat"><span className="quality-number">{dataQuality.total_observations}</span><span>Total Observations</span></div>
            <div className="quality-stat"><span className="quality-number">{dataQuality.synthetic_observations}</span><span>Synthetic (Demo)</span></div>
            <div className="quality-stat"><span className="quality-number">{dataQuality.validated_observations}</span><span>Validated</span></div>
            <div className="quality-stat"><span className="quality-number">{dataQuality.unvalidated_observations}</span><span>Unvalidated</span></div>
            <div className="quality-stat"><span className="quality-number">{dataQuality.flagged_observations}</span><span>Flagged</span></div>
            <div className="quality-stat"><span className="quality-number">{dataQuality.regions_with_data}/31</span><span>Regions With Data</span></div>
          </div>
        )}
        {dataQuality && dataQuality.regions_missing_data.length > 0 && (
          <p className="note" style={{ marginTop: '0.5rem' }}>
            <strong>No data available</strong> for: {dataQuality.regions_missing_data.join(', ')}
            {' '}(shown as "No data available", never estimated or copied from another region).
          </p>
        )}

        <h3 style={{ fontSize: '0.88rem', margin: '1rem 0 0.4rem' }}>Ingest Climate Observations (Interim Bridge)</h3>
        <p className="note">
          Upload a .csv or .xlsx of climate observations (region, year, month, rainfall_mm,
          avg_temperature_c, etc.). <strong>This is a temporary manual bridge, not the official
          TMA integration</strong> — it exists only because no real TMA API/feed access is
          available yet. The validation rules it runs are the same ones a future direct/automated
          TMA feed would use; once that exists, this manual step is no longer needed. See
          docs/TMA_INGESTION.md.
        </p>
        <form onSubmit={handleClimateUpload} style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <select value={climateSource} onChange={(e) => setClimateSource(e.target.value)}>
            <option value="MANUAL_UPLOAD">Manual Upload</option>
            <option value="TMA_FILE">TMA File</option>
          </select>
          <input
            placeholder="Dataset name (optional)"
            value={climateDatasetName}
            onChange={(e) => setClimateDatasetName(e.target.value)}
            style={{ maxWidth: 220 }}
          />
          <input
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={(e) => setClimateFile(e.target.files?.[0] || null)}
          />
          <button type="submit" disabled={climateUploading}>
            {climateUploading ? 'Ingesting...' : 'Ingest File'}
          </button>
        </form>
        {climateUploadMessage && <div className="alert-info" style={{ marginTop: '0.5rem' }}>{climateUploadMessage}</div>}

        <h3 style={{ fontSize: '0.88rem', margin: '1rem 0 0.4rem' }}>Recent Ingestion Batches</h3>
        <table>
          <thead><tr><th>When</th><th>Source</th><th>File</th><th>Received</th><th>Accepted</th><th>Rejected</th><th>Duplicate</th></tr></thead>
          <tbody>
            {ingestionBatches.map((b) => (
              <tr key={b.id}>
                <td>{new Date(b.created_at).toLocaleString()}</td>
                <td>{b.source}</td>
                <td>{b.file_name || '-'}</td>
                <td>{b.records_received}</td>
                <td>{b.records_accepted}</td>
                <td>{b.records_rejected}</td>
                <td>{b.records_duplicate}</td>
              </tr>
            ))}
            {ingestionBatches.length === 0 && <tr><td colSpan={7}>No ingestion batches yet.</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2>📊 Submission Status Distribution</h2>
        <PieChart segments={statusSegments.length ? statusSegments : [{ label: 'No data yet', value: 1, color: '#EDEBE3' }]} />
      </section>

      <section className="card" id="combined-section">
        <h2>🔗 Combined Climate-Financial Exposure</h2>
        <p className="note">
          Meteorological readings (rainfall, temperature, recorded hazards) joined with real
          loan/collateral exposure for the same region and reporting period — this is what
          directly links climate data to financial stability, rather than the two datasets
          sitting in separate, unrelated tables. A blank climate column means no meteorological
          reading exists for that region/period — it is never guessed or filled in.
        </p>
        {dataQuality && dataQuality.synthetic_observations > 0 && (
          <p className="alert-info" style={{ fontWeight: 600 }}>
            ⚠️ SYNTHETIC / DEMO DATA — {dataQuality.synthetic_observations} of the climate
            observations behind this table are demo data generated for this prototype, NOT
            official TMA readings. See the Climate Data Quality section above.
          </p>
        )}
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
                      {note.region || 'All regions'} · {note.hazard_type || 'General'} · by {note.created_by_name} · {new Date(note.created_at).toLocaleDateString()}
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
          <option value="SUPERSEDED">Superseded</option>
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
