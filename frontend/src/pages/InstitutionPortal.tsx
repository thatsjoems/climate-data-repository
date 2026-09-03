import { useEffect, useState, FormEvent } from 'react'
import apiClient from '../api/client'
import { useAuth } from '../context/AuthContext'
import PortalShell, { SidebarItem } from '../components/PortalShell'

interface Submission {
  id: string
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

const STATUS_LABELS: Record<string, string> = {
  PENDING: 'Pending',
  VALID: 'Valid',
  INVALID: 'Has Errors',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
}

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

export default function InstitutionPortal() {
  const { user } = useAuth()
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [reportingPeriod, setReportingPeriod] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadMessage, setUploadMessage] = useState<string | null>(null)
  const [selected, setSelected] = useState<{ submission: Submission; errors: ValidationErrorItem[] } | null>(null)

  async function loadSubmissions() {
    const res = await apiClient.get('/submissions')
    setSubmissions(res.data)
  }

  useEffect(() => {
    loadSubmissions()
  }, [])

  async function handleDownloadTemplate() {
    const res = await apiClient.get('/templates/loan-collateral/download', { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', 'CDR_Loan_Collateral_Template.xlsx')
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  async function handleUpload(e: FormEvent) {
    e.preventDefault()
    if (!file || !reportingPeriod) {
      setUploadMessage('Please select a file and enter a reporting period (e.g. 2026-Q3).')
      return
    }
    setUploading(true)
    setUploadMessage(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('reporting_period', reportingPeriod)
      const res = await apiClient.post('/submissions/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setUploadMessage(
        `Uploaded. Status: ${STATUS_LABELS[res.data.status] || res.data.status}. ` +
        `Valid records: ${res.data.valid_records}/${res.data.total_records}.`
      )
      setFile(null)
      setReportingPeriod('')
      loadSubmissions()
    } catch (err: any) {
      setUploadMessage(err?.response?.data?.detail || 'Failed to upload the file.')
    } finally {
      setUploading(false)
    }
  }

  async function viewDetails(submissionId: string) {
    const res = await apiClient.get(`/submissions/${submissionId}`)
    setSelected({ submission: res.data, errors: res.data.errors })
  }

  const totalSubmissions = submissions.length
  const pendingReview = submissions.filter((s) => s.status === 'VALID' || s.status === 'PENDING').length
  const approved = submissions.filter((s) => s.status === 'APPROVED').length

  const sidebarItems: SidebarItem[] = [
    { key: 'overview', icon: '🏠', label: 'Overview', active: true, onClick: () => scrollTo('top-anchor') },
    { key: 'download', icon: '📥', label: 'Download Template', onClick: () => scrollTo('download-card') },
    { key: 'upload', icon: '📤', label: 'Upload Data', onClick: () => scrollTo('upload-card') },
    { key: 'history', icon: '🗂️', label: 'Submitted Files', onClick: () => scrollTo('history-card') },
  ]

  return (
    <PortalShell
      theme="institution"
      brandTitle="Financial Institution Portal"
      brandSubtitle="Climate Data Repository"
      pageTitle="Overview"
      pageSubtitle={user?.role === 'INSTITUTION_USER' ? 'Your institution\'s reporting dashboard' : undefined}
      items={sidebarItems}
    >
      <div id="top-anchor" />

      <section className="kpi-grid-v2">
        <div className="kpi-card-v2">
          <div className="kpi-icon-box" style={{ background: '#E6F1FB' }}>📄</div>
          <div className="kpi-card-v2-text">
            <span className="kpi-label">Total Submissions</span>
            <span className="kpi-number">{totalSubmissions}</span>
          </div>
        </div>
        <div className="kpi-card-v2">
          <div className="kpi-icon-box" style={{ background: '#FAEEDA' }}>⏳</div>
          <div className="kpi-card-v2-text">
            <span className="kpi-label">Pending Review</span>
            <span className="kpi-number">{pendingReview}</span>
          </div>
        </div>
        <div className="kpi-card-v2">
          <div className="kpi-icon-box" style={{ background: '#EAF3DE' }}>✅</div>
          <div className="kpi-card-v2-text">
            <span className="kpi-label">Approved</span>
            <span className="kpi-number">{approved}</span>
          </div>
        </div>
      </section>

      <section className="action-card-grid">
        <div className="action-card" id="download-card">
          <div className="action-card-icon" style={{ background: '#E6F1FB', color: '#185FA5' }}>📥</div>
          <h3>Download Template</h3>
          <p>Download the official standardized template for reporting loan and collateral data.</p>
          <button className="btn-accent" onClick={handleDownloadTemplate}>Download Template</button>
        </div>

        <div className="action-card" id="upload-card">
          <div className="action-card-icon" style={{ background: '#FAEEDA', color: '#854F0B' }}>📤</div>
          <h3>Upload Data</h3>
          <p>Upload your completed template file for automated validation.</p>
          <form onSubmit={handleUpload} className="upload-form" style={{ maxWidth: 'none' }}>
            <label>Reporting Period (e.g. 2026-Q3)</label>
            <input
              type="text"
              value={reportingPeriod}
              onChange={(e) => setReportingPeriod(e.target.value)}
              placeholder="2026-Q3"
            />
            <label>Completed Excel file</label>
            <input
              type="file"
              accept=".xlsx,.xls"
              onChange={(e) => setFile(e.target.files ? e.target.files[0] : null)}
            />
            <button className="btn-accent" type="submit" disabled={uploading} style={{ alignSelf: 'stretch', textAlign: 'center' }}>
              {uploading ? 'Uploading...' : 'Submit Data'}
            </button>
          </form>
          {uploadMessage && <div className="alert-info">{uploadMessage}</div>}
        </div>
      </section>

      <section className="card" id="history-card">
        <h2>🗂️ Recent Submissions</h2>
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>Period</th>
              <th>Status</th>
              <th>Valid / Total</th>
              <th>Date</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {submissions.map((s) => (
              <tr key={s.id}>
                <td>{s.file_name}</td>
                <td>{s.reporting_period}</td>
                <td><span className={`badge badge-${s.status.toLowerCase()}`}>{STATUS_LABELS[s.status]}</span></td>
                <td>{s.valid_records}/{s.total_records}</td>
                <td>{new Date(s.created_at).toLocaleString()}</td>
                <td><button onClick={() => viewDetails(s.id)}>View</button></td>
              </tr>
            ))}
            {submissions.length === 0 && (
              <tr><td colSpan={6}>You have not uploaded any submissions yet.</td></tr>
            )}
          </tbody>
        </table>
      </section>

      {selected && (
        <section className="card">
          <h2>Submission Details: {selected.submission.file_name}</h2>
          {selected.submission.review_notes && (
            <p><strong>BOT Reviewer Notes:</strong> {selected.submission.review_notes}</p>
          )}
          {selected.errors.length === 0 ? (
            <p>No errors were found.</p>
          ) : (
            <table>
              <thead>
                <tr><th>Row</th><th>Column</th><th>Error</th><th>Severity</th></tr>
              </thead>
              <tbody>
                {selected.errors.map((err, idx) => (
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
          <button onClick={() => setSelected(null)}>Close</button>
        </section>
      )}
    </PortalShell>
  )
}
