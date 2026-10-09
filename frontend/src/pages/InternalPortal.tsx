import { useEffect, useRef, useState, FormEvent, CSSProperties } from 'react'
import apiClient from '../api/client'
import { useAuth } from '../context/AuthContext'
import PortalShell, { SidebarItem, PlatformStatus } from '../components/PortalShell'
import HazardMap, { RegionMapPoint } from '../components/HazardMap'
import { HAZARD_COLORS, HAZARD_NONE_COLOR } from '../data/hazardColors'
import PagerBar from '../components/PagerBar'
import IntegrationAccess from '../components/IntegrationAccess'
import PortfolioCharts from '../components/PortfolioCharts'

// Rows and findings of a submission are shown this many at a time (see PagerBar).
const DETAIL_PAGE = 50

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
  institution_name?: string
  file_name: string
  reporting_period: string
  status: string
  total_records: number
  valid_records: number
  invalid_records: number
  created_at: string
  review_notes?: string
}

interface ValidationErrorItem {
  row_number: number | null
  column_name: string | null
  error_description: string
  severity: string
}

interface SubmissionRecordItem {
  row_number: number
  customer_id: string | null
  loan_id: string | null
  loan_amount_tzs: number | null
  collateral_type: string | null
  collateral_value_tzs: number | null
  region: string | null
  district: string | null
  ward: string | null
  climate_hazard_exposure: string | null
  is_valid: boolean
}

interface HazardExposure {
  region: string
  hazard_type: string | null
  exposed_loan_amount_tzs: number
  exposed_collateral_value_tzs?: number
  record_count: number
}

interface KpiSource {
  submission_id: string
  institution_id: string
  institution_name: string
  reporting_period: string
  file_name: string
  version_number: number
  total_records: number
  valid_records: number
  invalid_records: number
  contributing_records: number
  loan_total_tzs: number
  collateral_total_tzs: number
  row_validity_pct: number | null
}

interface CombinedExposure {
  region: string
  reporting_period: string
  avg_rainfall_mm: number | null
  avg_temperature_c: number | null
  hazard_types_recorded: string[]
  climate_data_quality: string | null
  total_loan_exposure_tzs: number
  total_collateral_value_tzs: number
  record_count: number
}

interface RiskAdvisory {
  id: string
  title: string
  region: string | null
  hazard_type: string | null
  reporting_period: string | null
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

/**
 * Renders a KPI figure exactly like a plain `<span className="kpi-number">`
 * when it fits its card - same single-line, fixed-size, bold look as
 * before. Only when the real pixel width of the text is wider than the
 * card actually allows does it measure the overflow and slide the text
 * left just far enough to reveal the hidden end, then back, on a loop -
 * so a very large TZS figure is always fully readable without shrinking
 * the font or breaking the one-line layout for every other (shorter) card.
 */
function SlidingKpiNumber({ text }: { text: string }) {
  const wrapRef = useRef<HTMLSpanElement>(null)
  const numberRef = useRef<HTMLSpanElement>(null)
  const [overflowPx, setOverflowPx] = useState(0)

  useEffect(() => {
    function measure() {
      const wrap = wrapRef.current, num = numberRef.current
      if (!wrap || !num) return
      const diff = num.scrollWidth - wrap.clientWidth
      setOverflowPx(diff > 2 ? diff : 0)
    }
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [text])

  return (
    <span
      ref={wrapRef}
      className={`kpi-number-wrap${overflowPx > 0 ? ' is-overflowing' : ''}`}
      style={overflowPx > 0 ? ({ '--kpi-slide-distance': `-${overflowPx + 4}px` } as CSSProperties) : undefined}
    >
      <span ref={numberRef} className="kpi-number">{text}</span>
    </span>
  )
}

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

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

function buildReportingPeriodOptions(): string[] {
  const now = new Date()
  const currentYear = now.getFullYear()
  const options: string[] = []
  for (let year = currentYear + 1; year >= currentYear - 2; year--) {
    for (let q = 4; q >= 1; q--) {
      options.push(`${year}-Q${q}`)
    }
  }
  return options
}
const REPORTING_PERIOD_OPTIONS = buildReportingPeriodOptions()

export default function InternalPortal() {
  const { user } = useAuth()
  const [kpi, setKpi] = useState<KPI | null>(null)
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [hazardExposure, setHazardExposure] = useState<HazardExposure[]>([])
  const [combinedExposure, setCombinedExposure] = useState<CombinedExposure[]>([])
  const [validatedOnly, setValidatedOnly] = useState(true)
  const [institutions, setInstitutions] = useState<{ id: string; name: string }[]>([])
  const [filterInstitutionId, setFilterInstitutionId] = useState('')
  const [filterRegion, setFilterRegion] = useState('')
  const [filterReportingPeriod, setFilterReportingPeriod] = useState('')
  const [filterHazardType, setFilterHazardType] = useState('')
  const [showKpiSources, setShowKpiSources] = useState(false)
  const [kpiSources, setKpiSources] = useState<KpiSource[]>([])
  const [kpiSourcesError, setKpiSourcesError] = useState<string | null>(null)
  const [summaryText, setSummaryText] = useState('')
  const [summaryCopied, setSummaryCopied] = useState(false)
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [unvalidatedGroups, setUnvalidatedGroups] = useState<{ region: string; reporting_period: string; count: number }[]>([])
  const [qcMessage, setQcMessage] = useState<string | null>(null)
  const [qcReasons, setQcReasons] = useState<Record<string, string>>({})
  const [mapPoints, setMapPoints] = useState<RegionMapPoint[]>([])
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [notesById, setNotesById] = useState<Record<string, string>>({})
  const [selectedSubmission, setSelectedSubmission] = useState<{ submission: Submission; errors: ValidationErrorItem[]; records: SubmissionRecordItem[]; recordsTotal: number; errorsTotal: number; recordOffset: number; errorOffset: number } | null>(null)
  const [reportGenerating, setReportGenerating] = useState(false)
  const [reportMessage, setReportMessage] = useState<string | null>(null)
  const [riskAdvisories, setRiskAdvisories] = useState<RiskAdvisory[]>([])
  const [expandedNoteId, setExpandedNoteId] = useState<string | null>(null)
  const [advisoryForm, setAdvisoryForm] = useState({
    title: '', region: '', hazard_type: '', reporting_period: '', risk_level: 'MEDIUM', narrative: '', recommendation: '',
  })
  const [advisoryMessage, setAdvisoryMessage] = useState<string | null>(null)
  const [submittingAdvisory, setSubmittingAdvisory] = useState(false)
  const [dataQuality, setDataQuality] = useState<DataQuality | null>(null)
  const [ingestionBatches, setIngestionBatches] = useState<IngestionBatch[]>([])
  const [climateFile, setClimateFile] = useState<File | null>(null)
  const [climateSource, setClimateSource] = useState('MANUAL_TMA_FILE')
  const [climateDatasetName, setClimateDatasetName] = useState('')
  const [climateUploading, setClimateUploading] = useState(false)
  const [climateUploadMessage, setClimateUploadMessage] = useState<string | null>(null)

  const [climateQualityError, setClimateQualityError] = useState<string | null>(null)

  async function loadClimateQuality() {
    try {
      const [qRes, batchesRes, groupsRes] = await Promise.all([
        apiClient.get('/climate-data/quality-summary'),
        apiClient.get('/climate-data/ingestions'),
        apiClient.get('/climate-data/unvalidated-groups'),
      ])
      setDataQuality(qRes.data)
      setIngestionBatches(batchesRes.data)
      setUnvalidatedGroups(groupsRes.data)
      setClimateQualityError(null)
    } catch (err: any) {
      setClimateQualityError(
        err?.response?.status
          ? `Failed to load (HTTP ${err.response.status}): ${err.response.data?.detail || err.message}`
          : `Failed to load: ${err.message}`
      )
    }
  }

  async function handlePromoteClimateGroup(region: string, reportingPeriod: string, newFlag: 'VALIDATED' | 'FLAGGED') {
    setQcMessage(null)
    const key = `${region}-${reportingPeriod}`
    const reason = (qcReasons[key] || '').trim()
    if (newFlag === 'FLAGGED' && !reason) {
      setQcMessage(`Please provide a reason before flagging ${region} / ${reportingPeriod}.`)
      return
    }
    try {
      const res = await apiClient.post('/climate-data/promote', {
        region, reporting_period: reportingPeriod, new_quality_flag: newFlag, reason,
      })
      setQcMessage(`${res.data.records_updated} reading(s) for ${region} / ${reportingPeriod} marked ${newFlag}.`)
      setQcReasons((prev) => { const next = { ...prev }; delete next[key]; return next })
      loadClimateQuality()
      reloadClimateExposureViews(validatedOnly)
    } catch (err: any) {
      setQcMessage(err?.response?.data?.detail || 'Failed to update the climate readings.')
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
      if (err?.response?.data?.detail) {
        setClimateUploadMessage(err.response.data.detail)
      } else if (err?.response?.status) {
        setClimateUploadMessage(
          err.response.status === 413
            ? 'The file is too large for the server to accept (HTTP 413).'
            : `Failed to ingest the file (HTTP ${err.response.status}).`
        )
      } else {
        setClimateUploadMessage('Failed to ingest the file - no response from the server (network error or timeout).')
      }
    } finally {
      setClimateUploading(false)
    }
  }

  function buildFilterQuery(extra: Record<string, string | boolean> = {}) {
    const params = new URLSearchParams()
    if (filterInstitutionId) params.set('filter_institution_id', filterInstitutionId)
    if (filterRegion) params.set('filter_region', filterRegion)
    if (filterReportingPeriod) params.set('filter_reporting_period', filterReportingPeriod)
    if (filterHazardType) params.set('filter_hazard_type', filterHazardType)
    for (const [k, v] of Object.entries(extra)) params.set(k, String(v))
    return params.toString()
  }

  // The seven datasets load independently: if one fails the others are still shown, and the page says which one is missing
  // (before, a single failure left the whole dashboard empty).
  const [loadWarnings, setLoadWarnings] = useState<string[]>([])
  // The filters the portfolio charts were last loaded with: they change only when the filters are applied or reset,
  // exactly like the Summary Figures (not while a dropdown is being changed).
  const [chartQuery, setChartQuery] = useState('')

  async function loadAll() {
    const missing: string[] = []
    const part = async (label: string, request: Promise<any>, apply: (data: any) => void) => {
      try {
        apply((await request).data)
      } catch (err: any) {
        missing.push(label)
      }
    }
    await Promise.all([
      part('institutions', apiClient.get('/institutions'), setInstitutions),
      part('summary figures', apiClient.get(`/analytics/kpi-summary?${buildFilterQuery()}`), setKpi),
      part('submissions', apiClient.get('/submissions'), setSubmissions),
      part('hazard exposure', apiClient.get(`/analytics/hazard-exposure?${buildFilterQuery({ validated_only: validatedOnly })}`), setHazardExposure),
      part('combined exposure', apiClient.get(`/analytics/combined-climate-financial-exposure?${buildFilterQuery({ validated_only: validatedOnly })}`), setCombinedExposure),
      part('risk advisories', apiClient.get('/risk-advisories'), setRiskAdvisories),
      part('map points', apiClient.get(`/analytics/map-points?${buildFilterQuery({ validated_only: validatedOnly })}`), setMapPoints),
    ])
    setLoadWarnings(missing)
    setChartQuery(buildFilterQuery())
  }

  async function reloadClimateExposureViews(nextValidatedOnly: boolean) {
    const [hazardRes, combinedRes, mapRes] = await Promise.all([
      apiClient.get(`/analytics/hazard-exposure?${buildFilterQuery({ validated_only: nextValidatedOnly })}`),
      apiClient.get(`/analytics/combined-climate-financial-exposure?${buildFilterQuery({ validated_only: nextValidatedOnly })}`),
      apiClient.get(`/analytics/map-points?${buildFilterQuery({ validated_only: nextValidatedOnly })}`),
    ])
    setHazardExposure(hazardRes.data)
    setCombinedExposure(combinedRes.data)
    setMapPoints(mapRes.data)
  }

  async function applyDashboardFilters() {
    const [kpiRes, hazardRes, combinedRes, mapRes] = await Promise.all([
      apiClient.get(`/analytics/kpi-summary?${buildFilterQuery()}`),
      apiClient.get(`/analytics/hazard-exposure?${buildFilterQuery({ validated_only: validatedOnly })}`),
      apiClient.get(`/analytics/combined-climate-financial-exposure?${buildFilterQuery({ validated_only: validatedOnly })}`),
      apiClient.get(`/analytics/map-points?${buildFilterQuery({ validated_only: validatedOnly })}`),
    ])
    setKpi(kpiRes.data)
    setHazardExposure(hazardRes.data)
    setCombinedExposure(combinedRes.data)
    setMapPoints(mapRes.data)
    setChartQuery(buildFilterQuery())
    if (showKpiSources) loadKpiSources()
  }

  // Data lineage: the current APPROVED submissions behind the Summary Figures (same filters; the
  // hazard filter does not apply to these totals).
  async function loadKpiSources(query?: string) {
    setKpiSourcesError(null)
    try {
      const res = await apiClient.get(`/analytics/kpi-sources?${query !== undefined ? query : buildFilterQuery()}`)
      setKpiSources(res.data)
    } catch (err: any) {
      setKpiSources([])
      setKpiSourcesError('Could not load the sources of these figures. Please try again.')
    }
  }

  function toggleKpiSources() {
    const next = !showKpiSources
    setShowKpiSources(next)
    if (next) loadKpiSources()
  }

  async function openSourceRows(submissionId: string) {
    await viewSubmissionDetails(submissionId)
    setTimeout(() => document.getElementById('submission-details')?.scrollIntoView({ behavior: 'smooth' }), 150)
  }

  // Hide the summary draft again (it is never saved, so closing discards it).
  function closeSummary() {
    setSummaryOpen(false)
    setSummaryCopied(false)
  }

  // A draft supervisory summary built only from the approved figures currently on screen. Every
  // sentence states a measured value; nothing is estimated, compared with other periods, or rated.
  function buildSupervisorySummary(): string {
    if (!kpi) return 'No approved figures are available yet, so no summary can be generated.'
    const money = (n: number) => `TZS ${Math.round(n).toLocaleString('en-US')}`
    const pct = (part: number, whole: number) => (whole > 0 ? `${Math.round((1000 * part) / whole) / 10}%` : '0%')
    const scopeParts: string[] = []
    if (filterInstitutionId) {
      const inst = institutions.find((i) => i.id === filterInstitutionId)
      scopeParts.push(inst ? inst.name : 'one institution')
    }
    if (filterRegion) scopeParts.push(`region ${filterRegion}`)
    if (filterReportingPeriod) scopeParts.push(`reporting period ${filterReportingPeriod}`)
    if (filterHazardType) scopeParts.push(`hazard ${filterHazardType === 'None' ? 'none recorded' : filterHazardType} (hazard sections only)`)
    const lines: string[] = []
    lines.push(scopeParts.length ? `Scope: ${scopeParts.join('; ')}.` : 'Scope: sector-wide, all approved data.')
    lines.push(`Reported exposure: ${kpi.approved_submissions} approved submission(s) from ${kpi.total_institutions} reporting institution(s) show total loan exposure of ${money(kpi.total_loan_exposure_tzs)} against collateral valued at ${money(kpi.total_collateral_value_tzs)}.`)

    const totalsByHazard: Record<string, number> = {}
    let hazardTotal = 0
    for (const h of hazardExposure) {
      const key = h.hazard_type || 'None'
      totalsByHazard[key] = (totalsByHazard[key] || 0) + h.exposed_loan_amount_tzs
      hazardTotal += h.exposed_loan_amount_tzs
    }
    const recorded = Object.entries(totalsByHazard).filter(([k]) => k !== 'None').sort((a, b) => b[1] - a[1])
    if (recorded.length > 0 && hazardTotal > 0) {
      const topHazard = recorded[0][0]
      const topValue = recorded[0][1]
      const regionsForTop = new Set(hazardExposure.filter((h) => h.hazard_type === topHazard).map((h) => h.region)).size
      lines.push(`Hazard pattern: ${topHazard} is the most frequently recorded hazard for ${pct(topValue, hazardTotal)} of the loan exposure shown (${regionsForTop} region(s)). This describes a regional pattern, not the hazard at any individual loan's location.`)
      const noneValue = totalsByHazard['None'] || 0
      if (noneValue > 0) lines.push(`No hazard is recorded for ${pct(noneValue, hazardTotal)} of the exposure shown (regions or periods without climate readings).`)
    } else {
      lines.push('Hazard pattern: no hazard is recorded for the exposure shown.')
    }

    const byRegion: Record<string, number> = {}
    let regionTotal = 0
    for (const c of combinedExposure) {
      byRegion[c.region] = (byRegion[c.region] || 0) + c.total_loan_exposure_tzs
      regionTotal += c.total_loan_exposure_tzs
    }
    const regionsSorted = Object.entries(byRegion).sort((a, b) => b[1] - a[1])
    if (regionsSorted.length > 0 && regionTotal > 0) {
      lines.push(`Concentration: ${regionsSorted[0][0]} holds the largest share of the exposure shown, ${pct(regionsSorted[0][1], regionTotal)} (${money(regionsSorted[0][1])}).`)
    }

    if (combinedExposure.length > 0) {
      const validated = combinedExposure.filter((c) => c.climate_data_quality === 'VALIDATED').length
      const noClimate = combinedExposure.filter((c) => !c.climate_data_quality).length
      lines.push(`Climate data: ${validated} of ${combinedExposure.length} region-period rows rest on fully VALIDATED readings; ${combinedExposure.length - validated - noClimate} include unvalidated or synthetic readings; ${noClimate} have no climate readings (left blank, never estimated).`)
    }

    lines.push(`Submission tracking: ${kpi.valid_submissions} awaiting review, ${kpi.invalid_submissions} invalid and ${kpi.rejected_submissions} rejected (none of these is included in any figure above).`)
    lines.push('Basis: BOT-approved submissions only. This draft was generated from the figures shown on the dashboard; the analyst must review and edit it before use.')
    return lines.join('\n\n')
  }

  async function copySummary() {
    try {
      await navigator.clipboard.writeText(summaryText)
      setSummaryCopied(true)
    } catch (err: any) {
      setSummaryCopied(false)
    }
  }

  function resetDashboardFilters() {
    setFilterInstitutionId(''); setFilterRegion(''); setFilterReportingPeriod(''); setFilterHazardType('')
    setChartQuery('')
    apiClient.get(`/analytics/kpi-summary?validated_only=${validatedOnly}`).then((r) => setKpi(r.data))
    apiClient.get(`/analytics/hazard-exposure?validated_only=${validatedOnly}`).then((r) => setHazardExposure(r.data))
    apiClient.get(`/analytics/combined-climate-financial-exposure?validated_only=${validatedOnly}`).then((r) => setCombinedExposure(r.data))
    apiClient.get(`/analytics/map-points?validated_only=${validatedOnly}`).then((r) => setMapPoints(r.data))
    if (showKpiSources) loadKpiSources('')
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
        reporting_period: advisoryForm.reporting_period || null,
        recommendation: advisoryForm.recommendation || null,
      })
      setAdvisoryForm({ title: '', region: '', hazard_type: '', reporting_period: '', risk_level: 'MEDIUM', narrative: '', recommendation: '' })
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
      const res = await apiClient.get(`/reports/summary.pdf?${buildFilterQuery({ validated_only: validatedOnly })}`, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `CDR_Summary_Report_${new Date().toISOString().slice(0, 10)}.pdf`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      setReportMessage('Report generated and downloaded (reflects current Dashboard Filters, if any).')
    } catch (err: any) {
      setReportMessage('Failed to generate the report.')
    } finally {
      setReportGenerating(false)
    }
  }

  async function handleDownloadCombinedCsv() {
    const res = await apiClient.get(`/reports/combined-exposure.csv?${buildFilterQuery({ validated_only: validatedOnly })}`, { responseType: 'blob' })
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
      const res = await apiClient.get(`/reports/summary.xlsx?${buildFilterQuery({ validated_only: validatedOnly })}`, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `CDR_Summary_Report_${new Date().toISOString().slice(0, 10)}.xlsx`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      setReportMessage('Excel report generated and downloaded (reflects current Dashboard Filters, if any).')
    } catch (err: any) {
      setReportMessage('Failed to generate the Excel report.')
    } finally {
      setReportGenerating(false)
    }
  }

  async function handleGenerateReportImage() {
    setReportGenerating(true)
    setReportMessage(null)
    try {
      const res = await apiClient.get(`/reports/summary.png?${buildFilterQuery({ validated_only: validatedOnly })}`, { responseType: 'blob' })
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'image/png' }))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `CDR_Summary_Report_${new Date().toISOString().slice(0, 10)}.png`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      setReportMessage('Image snapshot generated and downloaded (reflects current Dashboard Filters, if any).')
    } catch (err: any) {
      setReportMessage('Failed to generate the image snapshot.')
    } finally {
      setReportGenerating(false)
    }
  }

  async function handleReview(submissionId: string, decision: 'APPROVE' | 'REJECT') {
    await apiClient.post(`/submissions/${submissionId}/review`, {
      decision,
      notes: notesById[submissionId] || '',
    })
    setSelectedSubmission(null)
    loadAll()
  }

  // Lets the analyst actually SEE the individual rows (customer, loan amount,
  // region...) before deciding Approve/Reject - not just the automated
  // valid/total counts. Automated validation can only catch what it was
  // told to check for (malformed GPS, missing fields, duplicate loan_id
  // within the file); it cannot catch a row that is well-formed but
  // fabricated or forged. This is exactly what "maker-checker" is supposed
  // to close - a technically-VALID submission is not the same claim as an
  // ANALYST-REVIEWED one, and until this button existed, the checker had no
  // way to actually check the content, only trust the machine's own pass/fail.
  // A submission can hold tens of thousands of rows and findings. Drawing them all at once froze the
  // browser ("Page unresponsive"), so the server sends one page of each and the panel pages through them.
  async function loadSubmissionDetails(submissionId: string, recordOffset = 0, errorOffset = 0) {
    const res = await apiClient.get(`/submissions/${submissionId}`, {
      params: { record_offset: recordOffset, record_limit: DETAIL_PAGE, error_offset: errorOffset, error_limit: DETAIL_PAGE },
    })
    setSelectedSubmission({
      submission: res.data, errors: res.data.errors, records: res.data.records,
      recordsTotal: res.data.records_total ?? res.data.records.length, errorsTotal: res.data.errors_total ?? res.data.errors.length,
      recordOffset, errorOffset,
    })
  }

  async function viewSubmissionDetails(submissionId: string) {
    await loadSubmissionDetails(submissionId, 0, 0)
    // The panel sits lower on the page than the button that opens it: bring it into view.
    window.setTimeout(() => document.getElementById('submission-details')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80)
  }

  const filteredSubmissions =
    statusFilter === 'ALL' ? submissions : submissions.filter((s) => s.status === statusFilter)

  // Hazard exposure matrix: the Hazard Exposure rows grouped by their dominant recorded hazard.
  // What the hazard filter means for the headline figures. The four Summary Figures are
  // deliberately NOT narrowed by hazard (a hazard is recorded per region, so a "flood total"
  // would be read as loans hit by floods). This line states the narrower number honestly:
  // exposure in the regions whose dominant recorded hazard is the chosen one.
  const hazardLabel = filterHazardType === 'None' ? 'no hazard recorded' : filterHazardType
  const hazardFocus = (() => {
    if (!filterHazardType) return null
    const loan = hazardExposure.reduce((acc, h) => acc + h.exposed_loan_amount_tzs, 0)
    const collateral = hazardExposure.reduce((acc, h) => acc + (h.exposed_collateral_value_tzs || 0), 0)
    const regions = new Set(hazardExposure.map((h) => h.region)).size
    const total = kpi ? kpi.total_loan_exposure_tzs : 0
    const share = total > 0 ? Math.round((1000 * loan) / total) / 10 : 0
    return { loan, collateral, regions, share }
  })()

  const hazardMatrix = (() => {
    const byHazard: Record<string, { loan: number; collateral: number; records: number; regions: Set<string> }> = {}
    for (const h of hazardExposure) {
      const key = h.hazard_type || 'None'
      if (!byHazard[key]) byHazard[key] = { loan: 0, collateral: 0, records: 0, regions: new Set<string>() }
      byHazard[key].loan += h.exposed_loan_amount_tzs
      byHazard[key].collateral += h.exposed_collateral_value_tzs || 0
      byHazard[key].records += h.record_count
      byHazard[key].regions.add(h.region)
    }
    return Object.entries(byHazard)
      .map(([hazard, v]) => ({ hazard, loan: v.loan, collateral: v.collateral, records: v.records, regions: v.regions.size }))
      .sort((a, b) => b.loan - a.loan)
  })()

  const sourcesTotals = kpiSources.reduce(
    (acc, src) => ({ rows: acc.rows + src.contributing_records, loan: acc.loan + src.loan_total_tzs, collateral: acc.collateral + src.collateral_total_tzs }),
    { rows: 0, loan: 0, collateral: 0 },
  )

  const statusSegments = kpi ? [
    { label: 'Pending', value: kpi.pending_submissions, color: '#94A3B8' },
    { label: 'Valid', value: kpi.valid_submissions, color: '#10B981' },
    { label: 'Invalid', value: kpi.invalid_submissions, color: '#F59E0B' },
    { label: 'Approved', value: kpi.approved_submissions, color: '#002B49' },
    { label: 'Rejected', value: kpi.rejected_submissions, color: '#EF4444' },
  ] : []

  const hazardTotals: Record<string, number> = {}
  hazardExposure.forEach((h) => {
    const key = h.hazard_type || 'None'
    hazardTotals[key] = (hazardTotals[key] || 0) + h.exposed_loan_amount_tzs
  })
  // Colors come from ../data/hazardColors - the single shared source with
  // the Geospatial Overview's Hazard layer (HazardMap.tsx), so a hazard's
  // color can never drift apart between the two screens. "None" is grey
  // specifically (HAZARD_NONE_COLOR, not cycled from the generic palette),
  // so an untagged/no-hazard slice reads as "nothing", not an arbitrary color.
  const hazardSegments = Object.entries(hazardTotals).map(([label, value]) => ({
    label, value, color: label === 'None' ? HAZARD_NONE_COLOR : HAZARD_COLORS[label] || '#94A3B8',
  }))

  // Real status from the server (a recently used read key for QGIS/ArcGIS, a successful health check for BSIS/RTIS);
  // until it answers, or if it fails, every platform shows as not connected.
  const [platforms, setPlatforms] = useState<PlatformStatus[]>([
    { name: 'ArcGIS', connected: false },
    { name: 'QGIS', connected: false },
    { name: 'BSIS', connected: false },
    { name: 'RTIS', connected: false },
  ])
  useEffect(() => {
    apiClient.get('/integration-clients/platform-status')
      .then((res) => setPlatforms(res.data.map((p: { name: string; connected: boolean }) => ({ name: p.name, connected: p.connected }))))
      .catch(() => { /* keep "not connected" */ })
  }, [])

  const sidebarItems: SidebarItem[] = [
    { key: 'overview', icon: '📊', label: 'Overview', active: true, onClick: () => scrollTo('top-anchor') },
    { key: 'automated-reports', icon: '📑', label: 'Automated Reports', onClick: () => scrollTo('reports-section') },
    { key: 'filters', icon: '🔍', label: 'Dashboard Filters', onClick: () => scrollTo('dashboard-filters') },
    { key: 'summary-figures', icon: '🔢', label: 'Summary Figures', onClick: () => scrollTo('kpi-section') },
    { key: 'portfolio', icon: '📈', label: 'Loan & Collateral Charts', onClick: () => scrollTo('portfolio-section') },
    { key: 'map', icon: '🗺️', label: 'Geospatial Map', onClick: () => scrollTo('map-section') },
    { key: 'climate', icon: '🌦️', label: 'Climate & Hazard Data', onClick: () => scrollTo('hazard-section') },
    { key: 'quality', icon: '📋', label: 'Climate Data Quality', onClick: () => scrollTo('quality-section') },
    { key: 'status-dist', icon: '📊', label: 'Submission Status Distribution', onClick: () => scrollTo('status-distribution-section') },
    { key: 'combined', icon: '🔗', label: 'Combined Climate-Financial', onClick: () => scrollTo('combined-section') },
    { key: 'risk', icon: '🧭', label: 'Risk Advisory Reports', onClick: () => scrollTo('risk-advisory-section') },
    { key: 'submissions', icon: '📄', label: 'Submission Status', onClick: () => scrollTo('monitoring-section') },
    { key: 'regional', icon: '🌍', label: 'Exposure by Region', onClick: () => scrollTo('regional-exposure-section') },
    { key: 'integration', icon: '🔌', label: 'Integration Access', onClick: () => scrollTo('integration-section') },
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

      {loadWarnings.length > 0 && (
        <div className="card" style={{ borderLeft: '4px solid #b42318' }}>
          <strong>Some parts of the dashboard could not be loaded:</strong> {loadWarnings.join(', ')}. The rest is shown.{' '}
          <button className="btn-secondary btn-sm" onClick={() => loadAll()}>Try again</button>
        </div>
      )}

      <section className="card" id="reports-section">
        <h2>⬇️ Automated Reports</h2>
        <p className="note">
          Compiles the current KPI summary, loan and collateral charts, climate hazard exposure, combined
          climate-financial exposure, and recent Risk Advisory Reports into PDF, Excel, or a single-image
          snapshot (following the Dashboard Filters you have applied) — the same figures shown on this
          dashboard, ready to file or share instead of copying numbers manually.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.6rem' }}>
          <button className="btn-accent" onClick={handleGenerateReport} disabled={reportGenerating}>
            {reportGenerating ? 'Generating...' : 'Generate Summary Report (PDF)'}
          </button>
          <button onClick={handleGenerateReportExcel} disabled={reportGenerating}>Generate Summary Report (Excel)</button>
          <button onClick={handleGenerateReportImage} disabled={reportGenerating}>Generate Summary Snapshot (Image)</button>
          <button onClick={handleDownloadCombinedCsv}>Download Combined Exposure (CSV)</button>
          <button
            onClick={() => { setSummaryText(buildSupervisorySummary()); setSummaryCopied(false); setSummaryOpen(true) }}
            style={{ gridColumn: '1 / -1', width: '100%' }}
          >
            Generate Supervisory Summary
          </button>
        </div>
        <div>
          {summaryOpen && (
            <div style={{ marginTop: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem', marginBottom: '0.4rem' }}>
                <p className="note" style={{ margin: 0 }}>
                  A draft written from the approved figures currently shown on this dashboard. Edit it as needed
                  before use; it is not saved or sent anywhere, so closing it discards the draft.
                </p>
                <button className="btn-secondary btn-sm" onClick={closeSummary} aria-label="Close the supervisory summary">Close</button>
              </div>
              <textarea
                value={summaryText}
                onChange={(e) => { setSummaryText(e.target.value); setSummaryCopied(false) }}
                rows={14}
                style={{ width: '100%' }}
              />
              <div style={{ marginTop: '0.4rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <button className="btn-secondary btn-sm" onClick={copySummary}>Copy to clipboard</button>
                <button className="btn-secondary btn-sm" onClick={closeSummary}>Close</button>
                {summaryCopied && <span className="note">Copied.</span>}
              </div>
            </div>
          )}
        </div>
        {reportMessage && <div className="alert-info">{reportMessage}</div>}
      </section>

      <section className="card" id="dashboard-filters">
        <h2>🔍 Dashboard Filters</h2>
        <p className="note">
          Narrow the Summary Figures, Hazard Exposure, and Combined Exposure below by institution,
          region, and/or reporting period. Filters only ever narrow the sector-wide view - they
          never widen access.
        </p>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.78rem', marginBottom: '0.2rem' }}>Institution</label>
            <select value={filterInstitutionId} onChange={(e) => setFilterInstitutionId(e.target.value)}>
              <option value="">All institutions</option>
              {institutions.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.78rem', marginBottom: '0.2rem' }}>Region</label>
            <select value={filterRegion} onChange={(e) => setFilterRegion(e.target.value)}>
              <option value="">All regions</option>
              {[...new Set(combinedExposure.map((c) => c.region))].sort().map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.78rem', marginBottom: '0.2rem' }}>Reporting Period</label>
            <select value={filterReportingPeriod} onChange={(e) => setFilterReportingPeriod(e.target.value)}>
              <option value="">All periods</option>
              {[...new Set([...combinedExposure.map((c) => c.reporting_period), ...submissions.map((s) => s.reporting_period)])].sort().reverse().map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.78rem', marginBottom: '0.2rem' }}>Hazard</label>
            <select value={filterHazardType} onChange={(e) => setFilterHazardType(e.target.value)}>
              <option value="">All hazards</option>
              {['Flood', 'Drought', 'Landslide', 'Cyclone', 'None'].map((h) => <option key={h} value={h}>{h === 'None' ? 'None recorded' : h}</option>)}
            </select>
          </div>
          <button className="btn-accent" onClick={applyDashboardFilters}>Apply Filters</button>
          <button onClick={resetDashboardFilters}>Reset</button>
        </div>
        <p className="note" style={{ marginTop: '0.6rem' }}>
          The Hazard filter keeps the regions whose dominant recorded hazard is the one chosen. It narrows
          Hazard Exposure, Combined Exposure, the map's region circles and the reports. It does not change
          the Summary Figures, the hazard surface (which needs every region) or the loan and collateral points.
        </p>
      </section>

      {kpi && (
        <section className="kpi-grid-v2" id="kpi-section">
          <h2 className="section-title" style={{ gridColumn: '1 / -1' }}>🔢 Summary Figures</h2>
          <p className="alert-info" style={{ gridColumn: '1 / -1', fontWeight: 600 }}>
            ✅ These figures reflect BOT-APPROVED submissions only. A submission that has
            passed automated validation but is still awaiting review does not appear here or
            anywhere else in these figures until a BOT Analyst approves it - see Submission
            Monitoring for its review status in the meantime.
          </p>
          <div className="kpi-card-v2">
            <div className="kpi-icon-box" style={{ background: '#FDF0DC' }}>💰</div>
            <div className="kpi-card-v2-text">
              <span className="kpi-label">Total Loan Value</span>
              <SlidingKpiNumber text={formatTZS(kpi.total_loan_exposure_tzs)} />
            </div>
          </div>
          <div className="kpi-card-v2">
            <div className="kpi-icon-box" style={{ background: '#E6F1FB' }}>🛡️</div>
            <div className="kpi-card-v2-text">
              <span className="kpi-label">Total Collateral Value</span>
              <SlidingKpiNumber text={formatTZS(kpi.total_collateral_value_tzs)} />
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
          {hazardFocus && (
            <div className="alert-info" style={{ gridColumn: '1 / -1' }}>
              <strong>Hazard focus: {hazardLabel}.</strong>{' '}
              {hazardFocus.regions === 0
                ? 'No region has this as its dominant recorded hazard for the current filters. '
                : `Loan exposure in the ${hazardFocus.regions} region(s) where this is the dominant recorded hazard: ${formatTZS(hazardFocus.loan)} (${hazardFocus.share}% of the total loan value above), with collateral of ${formatTZS(hazardFocus.collateral)}. `}
              The four figures above are not narrowed by hazard.
            </div>
          )}
          <div style={{ gridColumn: '1 / -1' }}>
            <button className="btn-secondary btn-sm" onClick={toggleKpiSources}>
              {showKpiSources ? 'Hide the source of these figures' : 'View the source of these figures'}
            </button>
          </div>
          {showKpiSources && (
            <div className="card" style={{ gridColumn: '1 / -1', margin: 0 }}>
              <h3 style={{ fontSize: '0.95rem', marginTop: 0 }}>Where these figures come from</h3>
              <p className="note">
                Each row is one APPROVED, current submission that feeds the figures above, under the
                same institution, region and period filters (the hazard filter does not apply to these
                totals). "Rows used" counts the valid rows that contribute. Row validity is valid rows
                divided by all rows in the file - a descriptive ratio, not a risk score. "View rows"
                opens the submitted rows and loan numbers.
              </p>
              {kpiSourcesError && <div className="alert-error">{kpiSourcesError}</div>}
              {!kpiSourcesError && kpiSources.length === 0 && <p className="note">No approved submission contributes under the current filters.</p>}
              {kpiSources.length > 0 && (
                <div style={{ overflowX: 'auto' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Institution</th><th>Period</th><th>File (version)</th><th>Rows used</th>
                        <th>Loan (TZS)</th><th>Collateral (TZS)</th><th>Row validity</th><th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {kpiSources.map((src) => (
                        <tr key={src.submission_id}>
                          <td>{src.institution_name}</td>
                          <td>{src.reporting_period}</td>
                          <td>{src.file_name} (v{src.version_number})</td>
                          <td>{src.contributing_records}</td>
                          <td>{Math.round(src.loan_total_tzs).toLocaleString('en-US')}</td>
                          <td>{Math.round(src.collateral_total_tzs).toLocaleString('en-US')}</td>
                          <td>{src.row_validity_pct === null ? '—' : `${src.row_validity_pct}%`}</td>
                          <td><button className="btn-sm" onClick={() => openSourceRows(src.submission_id)}>View rows</button></td>
                        </tr>
                      ))}
                      <tr style={{ fontWeight: 700 }}>
                        <td colSpan={3}>Total of these sources</td>
                        <td>{sourcesTotals.rows}</td>
                        <td>{Math.round(sourcesTotals.loan).toLocaleString('en-US')}</td>
                        <td>{Math.round(sourcesTotals.collateral).toLocaleString('en-US')}</td>
                        <td colSpan={2}></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {kpi && <PortfolioCharts filterQuery={chartQuery} />}

      <section className="card" id="map-section">
        <h2>🗺️ Geospatial Overview — Hazard Exposure & Portfolio</h2>
        <p className="note">
          Region-level view: circle size shows total loan exposure, color shows the dominant reported
          climate hazard for that region. Coordinates are region centroids (not exact loan locations) —
          precise per-loan mapping will follow once BOT's data template includes coordinates. Click a
          circle for details.
        </p>
        {filterHazardType && (
          <p className="alert-info">
            Hazard filter active ({filterHazardType === 'None' ? 'none recorded' : filterHazardType}): the region
            circles show only regions whose dominant recorded hazard matches. The hazard surface and the loan and
            collateral points are not narrowed by this filter.
          </p>
        )}
        {mapPoints.length > 0 || filterHazardType ? (
          <>
            {filterHazardType && (
              <p className="alert-info">
                {mapPoints.length === 0
                  ? `No region has "${hazardLabel}" as its dominant recorded hazard for the current filters, so no region markers are shown. `
                  : `Hazard filter on: ${mapPoints.length} region marker(s) where "${hazardLabel}" is the dominant recorded hazard. `}
                The hazard layer below follows this filter; the hazard surface and the loan and collateral points are not narrowed by hazard.
              </p>
            )}
            <HazardMap
              points={mapPoints}
              filterRegion={filterRegion}
              filterInstitutionId={filterInstitutionId}
              filterReportingPeriod={filterReportingPeriod}
              filterHazardType={filterHazardType}
            />
          </>
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
        <p className="note">
          Share of valid loan exposure in regions/periods where each hazard was the most-frequently
          recorded climate observation - a regional pattern, not a claim about any individual loan.
        </p>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.82rem', marginBottom: '0.75rem' }}>
          <input
            type="checkbox"
            checked={validatedOnly}
            onChange={(e) => { setValidatedOnly(e.target.checked); reloadClimateExposureViews(e.target.checked) }}
          />
          Show VALIDATED climate readings only (affects this chart and Combined Exposure below — for
          official/supervisory use; leave unchecked to include SYNTHETIC/UNVALIDATED demo data too)
        </label>
        <PieChart segments={hazardSegments.length ? hazardSegments : [{ label: 'No data yet', value: 1, color: '#EDEBE3' }]} />
        {hazardMatrix.length > 0 && (
          <div style={{ overflowX: 'auto', marginTop: '1rem' }}>
            <h3 style={{ fontSize: '0.9rem', margin: '0 0 0.4rem' }}>Hazard exposure matrix</h3>
            <table>
              <thead>
                <tr><th>Hazard (dominant recorded)</th><th>Loan exposure (TZS)</th><th>Collateral (TZS)</th><th>Records</th><th>Regions</th></tr>
              </thead>
              <tbody>
                {hazardMatrix.map((m) => (
                  <tr key={m.hazard}>
                    <td>{m.hazard === 'None' ? 'None recorded' : m.hazard}</td>
                    <td>{Math.round(m.loan).toLocaleString('en-US')}</td>
                    <td>{Math.round(m.collateral).toLocaleString('en-US')}</td>
                    <td>{m.records}</td>
                    <td>{m.regions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="note" style={{ marginTop: '0.4rem' }}>
              Each region and period is counted under one dominant recorded hazard, so the rows add up to the total
              without double counting. This is a regional pattern, not the hazard at an individual loan's location.
            </p>
          </div>
        )}
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
            <button className="btn-secondary btn-sm" style={{ marginLeft: '0.75rem' }} onClick={loadClimateQuality}>Retry</button>
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
        <p className="note" style={{ fontWeight: 600 }}>
          ⚠️ Self-declared source — the option below is your own belief about where the file came
          from; it is not independently verified. Do not select "TMA" or "PMO" unless you are
          confident of the actual origin.
        </p>
        <form onSubmit={handleClimateUpload} style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <select value={climateSource} onChange={(e) => setClimateSource(e.target.value)}>
            <option value="MANUAL_TMA_FILE">File I believe is from TMA</option>
            <option value="MANUAL_PMO_FILE">File I believe is from PMO</option>
            <option value="MANUAL_OTHER_FILE">Other source</option>
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

        <h3 style={{ fontSize: '0.88rem', margin: '1rem 0 0.4rem' }}>Climate Quality Control — Readings Awaiting Review</h3>
        <p className="note">
          A human review action: mark all UNVALIDATED readings for a region/period as VALIDATED
          (fit to inform official analytics and Risk Advisory Notes) or FLAGGED (rejected -
          excluded from every calculation). SYNTHETIC demo data and already-decided readings are
          never touched by this action.
        </p>
        {qcMessage && <div className="alert-info">{qcMessage}</div>}
        <table>
          <thead><tr><th>Region</th><th>Reporting Period</th><th>Unvalidated Readings</th><th>Reason (recommended, esp. for Flag)</th><th>Action</th></tr></thead>
          <tbody>
            {unvalidatedGroups.map((g) => (
              <tr key={`${g.region}-${g.reporting_period}`}>
                <td>{g.region}</td>
                <td>{g.reporting_period}</td>
                <td>{g.count}</td>
                <td>
                  <input
                    type="text"
                    placeholder="e.g. Cross-checked against station report"
                    value={qcReasons[`${g.region}-${g.reporting_period}`] || ''}
                    onChange={(e) => setQcReasons((prev) => ({ ...prev, [`${g.region}-${g.reporting_period}`]: e.target.value }))}
                    style={{ width: '100%', minWidth: 180 }}
                  />
                </td>
                <td>
                  <div className="button-row">
                    <button className="btn-sm btn-success" onClick={() => handlePromoteClimateGroup(g.region, g.reporting_period, 'VALIDATED')}>
                      ✓ Validate
                    </button>
                    <button className="btn-sm btn-danger" onClick={() => handlePromoteClimateGroup(g.region, g.reporting_period, 'FLAGGED')}>
                      ✕ Flag as Bad Data
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {unvalidatedGroups.length === 0 && <tr><td colSpan={5}>Nothing awaiting review right now.</td></tr>}
          </tbody>
        </table>

        <h3 style={{ fontSize: '0.88rem', margin: '1rem 0 0.4rem' }}>Recent Ingestion Batches</h3>
        <p className="note" style={{ marginTop: 0 }}>
          MANUAL_*: a BOT analyst uploaded the file. API_KEY_TMA and API_KEY_PMO: a system delivered it with a key issued by a BOT analyst; the label names the channel, not a verified sender. Everything delivered arrives as unvalidated and is used in the analysis only after an analyst promotes it.
        </p>
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

      <section className="card" id="status-distribution-section">
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
          reading exists for that region/period — it is never guessed or filled in. The
          "Climate Quality" column states plainly whether the figure is fully VALIDATED or a
          mix that includes unvalidated/synthetic readings — never a single blended number
          pretending to be uniformly reliable.
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
              <th>Hazards Recorded</th><th>Climate Quality</th><th>Loan Exposure</th><th>Collateral</th><th>Records</th>
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
                <td>
                  {c.climate_data_quality === 'VALIDATED' && <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>✓ VALIDATED</span>}
                  {c.climate_data_quality && c.climate_data_quality !== 'VALIDATED' && <span style={{ color: 'var(--color-warning)', fontWeight: 600 }}>⚠️ {c.climate_data_quality}</span>}
                  {!c.climate_data_quality && '—'}
                </td>
                <td>{formatTZS(c.total_loan_exposure_tzs)}</td>
                <td>{formatTZS(c.total_collateral_value_tzs)}</td>
                <td>{c.record_count}</td>
              </tr>
            ))}
            {combinedExposure.length === 0 && <tr><td colSpan={9}>No matching data yet.</td></tr>}
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
            <label>Reporting Period (optional — strongly recommended when a Region is set, so the attached climate reading matches the same period as the financial figures)</label>
            <select
              value={advisoryForm.reporting_period}
              onChange={(e) => setAdvisoryForm({ ...advisoryForm, reporting_period: e.target.value })}
            >
              <option value="">-- Not period-specific --</option>
              {REPORTING_PERIOD_OPTIONS.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
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
                      {note.region || 'All regions'} · {note.reporting_period || 'Not period-specific'} · {note.hazard_type || 'General'} · by {note.created_by_name} · {new Date(note.created_at).toLocaleDateString()}
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
                              {' '}({snapshot.latest_climate_reading.source} · {snapshot.latest_climate_reading.quality_flag || 'UNVALIDATED'})
                            </>
                          )}
                          {snapshot.climate_data_note && (
                            <>
                              <br />
                              <span style={{ color: 'var(--color-warning)' }}>⚠️ {snapshot.climate_data_note}</span>
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
              <th>Institution</th><th>File</th><th>Period</th><th>Status</th><th>Valid/Total</th><th>Row validity</th><th>Date</th>
              {(user?.role === 'BOT_USER' || user?.role === 'SYSTEM_ADMIN') && <th>Notes + Decision</th>}
            </tr>
          </thead>
          <tbody>
            {filteredSubmissions.map((s) => (
              <tr key={s.id}>
                <td><strong>{s.institution_name || institutions.find((i) => i.id === s.institution_id)?.name || '—'}</strong></td>
                <td>{s.file_name}</td>
                <td>{s.reporting_period}</td>
                <td><span className={`badge badge-${s.status.toLowerCase()}`}>{s.status === 'APPROVED' ? 'Approved✅' : s.status === 'REJECTED' ? 'Rejected❌' : s.status}</span></td>
                <td>{s.valid_records}/{s.total_records}</td>
                <td>{s.total_records > 0 ? `${Math.round((1000 * s.valid_records) / s.total_records) / 10}%` : '—'}</td>
                <td>{new Date(s.created_at).toLocaleDateString()}</td>
                {(user?.role === 'BOT_USER' || user?.role === 'SYSTEM_ADMIN') && (
                  <td>
                    {['APPROVED', 'REJECTED', 'SUPERSEDED'].includes(s.status) ? (
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem' }}>
                        <button className="btn-sm" onClick={() => viewSubmissionDetails(s.id)}>View Details</button>
                        <span className="note" style={{ fontStyle: 'italic', gridColumn: '2 / 3' }}>
                          Already {s.status === 'APPROVED' ? 'Approved✅' : s.status === 'REJECTED' ? 'Rejected❌' : s.status.toLowerCase()} - final.
                        </span>
                      </div>
                    ) : (
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem' }}>
                        <button className="btn-sm" onClick={() => viewSubmissionDetails(s.id)}>View Details</button>
                        <button className="btn-sm" onClick={() => handleReview(s.id, 'APPROVE')}>Approve</button>
                        <input
                          type="text"
                          placeholder="Notes (optional)"
                          value={notesById[s.id] || ''}
                          onChange={(e) => setNotesById({ ...notesById, [s.id]: e.target.value })}
                        />
                        <button className="btn-sm" onClick={() => handleReview(s.id, 'REJECT')}>Reject</button>
                      </div>
                    )}
                  </td>
                )}
              </tr>
            ))}
            {filteredSubmissions.length === 0 && (
              <tr><td colSpan={8}>No submissions match this filter.</td></tr>
            )}
          </tbody>
        </table>
      </section>

      {selectedSubmission && (
        <section className="card" id="submission-details">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <h2 style={{ margin: 0 }}>Submission Details: {selectedSubmission.submission.institution_name || institutions.find((i) => i.id === selectedSubmission.submission.institution_id)?.name || '—'} · {selectedSubmission.submission.file_name}</h2>
            <button className="btn-secondary btn-sm" onClick={() => setSelectedSubmission(null)}>Close</button>
          </div>
          <p className="note">
            Row-level content of this submission - what the analyst is actually approving or
            rejecting, not just the automated valid/total counts above. Automated checks catch
            malformed data; they cannot judge whether a well-formed row is genuine.
          </p>
          {selectedSubmission.submission.review_notes && (
            <p><strong>Previous Reviewer Notes:</strong> {selectedSubmission.submission.review_notes}</p>
          )}

          <h3 style={{ fontSize: '0.88rem', marginBottom: '0.3rem' }}>Submitted Records</h3>
          <PagerBar noun="rows" total={selectedSubmission.recordsTotal} offset={selectedSubmission.recordOffset} pageSize={DETAIL_PAGE}
            onChange={(o) => loadSubmissionDetails(selectedSubmission.submission.id, o, selectedSubmission.errorOffset)} />
          {selectedSubmission.records.length === 0 ? (
            <p className="note">No records were found in this submission.</p>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th>Row</th><th>Customer ID</th><th>Loan ID</th><th>Loan Amount</th>
                    <th>Collateral Type</th><th>Collateral Value</th><th>Region</th><th>District</th><th>Ward</th><th>Hazard</th><th>Valid?</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedSubmission.records.map((r) => (
                    <tr key={r.row_number}>
                      <td>{r.row_number}</td>
                      <td>{r.customer_id ?? '-'}</td>
                      <td>{r.loan_id ?? '-'}</td>
                      <td>{r.loan_amount_tzs?.toLocaleString() ?? '-'}</td>
                      <td>{r.collateral_type ?? '-'}</td>
                      <td>{r.collateral_value_tzs?.toLocaleString() ?? '-'}</td>
                      <td>{r.region ?? '-'}</td>
                      <td>{r.district ?? '-'}</td>
                      <td>{r.ward ?? '-'}</td>
                      <td>{r.climate_hazard_exposure ?? '-'}</td>
                      <td>{r.is_valid ? '✅' : '❌'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h3 style={{ fontSize: '0.88rem', margin: '1rem 0 0.3rem' }}>Validation Errors</h3>
          <PagerBar noun="findings" total={selectedSubmission.errorsTotal} offset={selectedSubmission.errorOffset} pageSize={DETAIL_PAGE}
            onChange={(o) => loadSubmissionDetails(selectedSubmission.submission.id, selectedSubmission.recordOffset, o)} />
          {selectedSubmission.errors.length === 0 ? (
            <p>No errors were found.</p>
          ) : (
            <table>
              <thead>
                <tr><th>Row</th><th>Column</th><th>Error</th><th>Severity</th></tr>
              </thead>
              <tbody>
                {selectedSubmission.errors.map((err, idx) => (
                  <tr key={idx}>
                    <td>{err.row_number ?? '-'}</td>
                    <td>{err.column_name ?? '-'}</td>
                    <td>{err.error_description}</td>
                    <td>{err.severity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div style={{ marginTop: '0.75rem', display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}>
            {['APPROVED', 'REJECTED', 'SUPERSEDED'].includes(selectedSubmission.submission.status) ? (
              <span className="note" style={{ fontStyle: 'italic' }}>
                Already {selectedSubmission.submission.status === 'APPROVED' ? 'Approved✅' : selectedSubmission.submission.status === 'REJECTED' ? 'Rejected❌' : selectedSubmission.submission.status.toLowerCase()} - this decision is final and cannot be changed.
              </span>
            ) : (
              <>
                <input
                  type="text"
                  placeholder="Notes (optional)"
                  value={notesById[selectedSubmission.submission.id] || ''}
                  onChange={(e) => setNotesById({ ...notesById, [selectedSubmission.submission.id]: e.target.value })}
                  style={{ minWidth: 180 }}
                />
                <button className="btn-success" onClick={() => handleReview(selectedSubmission.submission.id, 'APPROVE')}>Approve</button>
                <button className="btn-danger" onClick={() => handleReview(selectedSubmission.submission.id, 'REJECT')}>Reject</button>
              </>
            )}
            <button className="btn-secondary" onClick={() => setSelectedSubmission(null)}>Close</button>
          </div>
        </section>
      )}

      <section className="card" id="regional-exposure-section">
        <h2>🌍 Climate & Financial Exposure by Region</h2>
        <p className="note">
          Loan value in regions/periods where this hazard was the most-frequently recorded climate
          observation - this describes the region's recorded climate pattern, not a claim that
          each individual loan itself was directly affected by that hazard.
        </p>
        <table>
          <thead><tr><th>Region</th><th>Recorded Hazard</th><th>Loan Exposure in Region/Period</th><th>Record Count</th></tr></thead>
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
      <IntegrationAccess canCreate />
    </PortalShell>
  )
}
