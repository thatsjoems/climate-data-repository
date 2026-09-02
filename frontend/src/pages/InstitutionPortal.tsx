import { useEffect, useState, FormEvent } from 'react'
import apiClient from '../api/client'

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

export default function InstitutionPortal() {
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

  return (
    <div className="page">
      <h1>Reporting Institution Portal</h1>

      <section className="card">
        <h2>1. Download the Standardized Template</h2>
        <p>Download the Excel template, fill it in with your loan/collateral data, then upload it below.</p>
        <button onClick={handleDownloadTemplate}>Download Template (.xlsx)</button>
      </section>

      <section className="card">
        <h2>2. Upload Data</h2>
        <form onSubmit={handleUpload} className="upload-form">
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
          <button type="submit" disabled={uploading}>
            {uploading ? 'Uploading...' : 'Upload'}
          </button>
        </form>
        {uploadMessage && <div className="alert-info">{uploadMessage}</div>}
      </section>

      <section className="card">
        <h2>3. Submission History</h2>
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
    </div>
  )
}
