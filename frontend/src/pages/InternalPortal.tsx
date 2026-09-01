import { useEffect, useState } from 'react'
import apiClient from '../api/client'
import { useAuth } from '../context/AuthContext'

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

function formatTZS(n: number) {
  return new Intl.NumberFormat('en-TZ', { maximumFractionDigits: 0 }).format(n) + ' TZS'
}

export default function InternalPortal() {
  const { user } = useAuth()
  const [kpi, setKpi] = useState<KPI | null>(null)
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [hazardExposure, setHazardExposure] = useState<HazardExposure[]>([])
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [notesById, setNotesById] = useState<Record<string, string>>({})

  async function loadAll() {
    const [kpiRes, subsRes, hazardRes] = await Promise.all([
      apiClient.get('/analytics/kpi-summary'),
      apiClient.get('/submissions'),
      apiClient.get('/analytics/hazard-exposure'),
    ])
    setKpi(kpiRes.data)
    setSubmissions(subsRes.data)
    setHazardExposure(hazardRes.data)
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

  return (
    <div className="page">
      <h1>Dashboard ya Ndani (Bank of Tanzania)</h1>

      {kpi && (
        <section className="kpi-grid">
          <div className="kpi-card"><span className="kpi-value">{kpi.total_institutions}</span><span>Taasisi Zinazoripoti</span></div>
          <div className="kpi-card"><span className="kpi-value">{kpi.total_submissions}</span><span>Jumla ya Submissions</span></div>
          <div className="kpi-card"><span className="kpi-value">{kpi.pending_submissions}</span><span>Zinazosubiri</span></div>
          <div className="kpi-card"><span className="kpi-value">{kpi.invalid_submissions}</span><span>Zenye Makosa</span></div>
          <div className="kpi-card"><span className="kpi-value">{kpi.approved_submissions}</span><span>Zilizokubaliwa</span></div>
          <div className="kpi-card"><span className="kpi-value">{kpi.rejected_submissions}</span><span>Zilizokataliwa</span></div>
          <div className="kpi-card wide"><span className="kpi-value">{formatTZS(kpi.total_loan_exposure_tzs)}</span><span>Jumla ya Mikopo (Valid Records)</span></div>
          <div className="kpi-card wide"><span className="kpi-value">{formatTZS(kpi.total_collateral_value_tzs)}</span><span>Jumla ya Collateral</span></div>
        </section>
      )}

      <section className="card">
        <h2>Ufuatiliaji wa Submissions (Submission Monitoring)</h2>
        <label>Chuja kwa Status: </label>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="ALL">Zote</option>
          <option value="PENDING">Pending</option>
          <option value="VALID">Valid</option>
          <option value="INVALID">Invalid</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
        </select>

        <table>
          <thead>
            <tr>
              <th>Faili</th><th>Kipindi</th><th>Status</th><th>Sahihi/Jumla</th><th>Tarehe</th>
              {(user?.role === 'BOT_USER' || user?.role === 'SYSTEM_ADMIN') && <th>Maoni + Uamuzi</th>}
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
                      placeholder="Maoni (hiari)"
                      value={notesById[s.id] || ''}
                      onChange={(e) => setNotesById({ ...notesById, [s.id]: e.target.value })}
                    />
                    <button onClick={() => handleReview(s.id, 'APPROVE')}>Kubali</button>
                    <button onClick={() => handleReview(s.id, 'REJECT')}>Kataa</button>
                  </td>
                )}
              </tr>
            ))}
            {filteredSubmissions.length === 0 && (
              <tr><td colSpan={6}>Hakuna submissions zinazolingana na chujio hili.</td></tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2>Climate & Financial Exposure kwa Mkoa</h2>
        <p className="note">Inaonyesha jumla ya thamani ya mikopo (kutoka submissions halali) kwa kila mkoa na hatari ya kimazingira iliyoripotiwa.</p>
        <table>
          <thead><tr><th>Mkoa</th><th>Hatari (Hazard)</th><th>Mikopo Iliyowekwa Wazi</th><th>Idadi ya Rekodi</th></tr></thead>
          <tbody>
            {hazardExposure.map((h, idx) => (
              <tr key={idx}>
                <td>{h.region}</td>
                <td>{h.hazard_type || 'None'}</td>
                <td>{formatTZS(h.exposed_loan_amount_tzs)}</td>
                <td>{h.record_count}</td>
              </tr>
            ))}
            {hazardExposure.length === 0 && <tr><td colSpan={4}>Hakuna data bado.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  )
}
