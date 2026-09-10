import { useEffect, useState, FormEvent } from 'react'
import apiClient from '../api/client'
import PortalShell, { SidebarItem, PlatformStatus } from '../components/PortalShell'

interface UserItem {
  id: string
  full_name: string
  username: string
  email: string
  role: string
  institution_id: string | null
  is_active: boolean
}

interface InstitutionItem {
  id: string
  code: string
  name: string
  type: string
  is_active: boolean
}

interface PasswordResetItem {
  id: string
  username: string
  full_name: string
  status: string
  created_at: string
}

interface AuditLogItem {
  id: string
  user_id: string | null
  action: string
  entity_type: string | null
  entity_id: string | null
  details: string | null
  created_at: string
}

export default function AdminPanel() {
  const [users, setUsers] = useState<UserItem[]>([])
  const [institutions, setInstitutions] = useState<InstitutionItem[]>([])
  const [message, setMessage] = useState<string | null>(null)

  const [newUser, setNewUser] = useState({
    full_name: '', username: '', email: '', password: '', role: 'INSTITUTION_USER', institution_id: '',
  })
  const [newInstitution, setNewInstitution] = useState({ code: '', name: '', type: 'BANK' })
  const [passwordResets, setPasswordResets] = useState<PasswordResetItem[]>([])
  const [generatedResetPassword, setGeneratedResetPassword] = useState<{ username: string; password: string; emailSent: boolean } | null>(null)
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([])
  const [auditTotal, setAuditTotal] = useState(0)
  const [auditOffset, setAuditOffset] = useState(0)
  const [auditActionFilter, setAuditActionFilter] = useState('')
  const AUDIT_PAGE_SIZE = 25

  async function loadAll() {
    const [usersRes, instRes, resetRes] = await Promise.all([
      apiClient.get('/users'),
      apiClient.get('/institutions'),
      apiClient.get('/password-reset-requests'),
    ])
    setUsers(usersRes.data)
    setInstitutions(instRes.data)
    setPasswordResets(resetRes.data)
    loadAuditLogs(0)
  }

  async function loadAuditLogs(offset: number) {
    const params = new URLSearchParams({ limit: String(AUDIT_PAGE_SIZE), offset: String(offset) })
    if (auditActionFilter) params.set('action', auditActionFilter)
    const res = await apiClient.get(`/audit-logs?${params.toString()}`)
    setAuditLogs(offset === 0 ? res.data.items : [...auditLogs, ...res.data.items])
    setAuditTotal(res.data.total)
    setAuditOffset(offset)
  }

  async function handleExportAuditLog() {
    const params = new URLSearchParams()
    if (auditActionFilter) params.set('action', auditActionFilter)
    const res = await apiClient.get(`/audit-logs/export.csv?${params.toString()}`, { responseType: 'blob' })
    const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `CDR_Audit_Log_${new Date().toISOString().slice(0, 10)}.csv`)
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  async function handleApprovePasswordReset(id: string) {
    setMessage(null)
    try {
      const res = await apiClient.post(`/password-reset-requests/${id}/approve`, {})
      setGeneratedResetPassword({
        username: res.data.request.username,
        password: res.data.new_temporary_password,
        emailSent: res.data.email_sent,
      })
      loadAll()
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || 'Failed to approve the password reset.')
    }
  }

  async function handleRejectPasswordReset(id: string) {
    const notes = window.prompt('Reason for rejecting this reset request (optional):') || ''
    try {
      await apiClient.post(`/password-reset-requests/${id}/reject`, { notes })
      loadAll()
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || 'Failed to reject the request.')
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  async function handleCreateUser(e: FormEvent) {
    e.preventDefault()
    setMessage(null)
    try {
      await apiClient.post('/users', {
        ...newUser,
        institution_id: newUser.institution_id || null,
      })
      setMessage('User added successfully.')
      setNewUser({ full_name: '', username: '', email: '', password: '', role: 'INSTITUTION_USER', institution_id: '' })
      loadAll()
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || 'Failed to add user.')
    }
  }

  async function handleCreateInstitution(e: FormEvent) {
    e.preventDefault()
    setMessage(null)
    try {
      await apiClient.post('/institutions', newInstitution)
      setMessage('Institution added successfully.')
      setNewInstitution({ code: '', name: '', type: 'BANK' })
      loadAll()
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || 'Failed to add institution.')
    }
  }

  async function toggleUserActive(u: UserItem) {
    const action = u.is_active ? 'deactivate' : 'activate'
    await apiClient.patch(`/users/${u.id}/${action}`)
    loadAll()
  }

  function scrollTo(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const platforms: PlatformStatus[] = [
    { name: 'ArcGIS', connected: false },
    { name: 'QGIS', connected: false },
    { name: 'BSIS', connected: false },
    { name: 'RTIS', connected: false },
  ]

  const sidebarItems: SidebarItem[] = [
    { key: 'resets', icon: '🔑', label: 'Password Resets', active: true, onClick: () => scrollTo('password-resets-card') },
    { key: 'institutions', icon: '🏢', label: 'Institutions', onClick: () => scrollTo('institutions-card') },
    { key: 'users', icon: '👥', label: 'Users', onClick: () => scrollTo('users-card') },
  ]

  return (
    <PortalShell
      theme="bot"
      brandTitle="Climate Data Repository"
      brandSubtitle="Bank of Tanzania"
      pageTitle="System Administration"
      pageSubtitle="Identity, access, and institution management"
      items={sidebarItems}
      platforms={platforms}
    >
      {message && <div className="alert-info">{message}</div>}

      {generatedResetPassword && (
        <section className="card" style={{ borderLeft: '3px solid var(--color-accent)' }}>
          <h2>🔑 Password Reset</h2>
          {generatedResetPassword.emailSent ? (
            <p>An email with the new password was sent automatically to the user.</p>
          ) : (
            <p>
              Email delivery is not configured in this environment — share this new password
              with the user through a verified channel (phone/official email) yourself.
            </p>
          )}
          <p>
            <strong>Username:</strong> <code>{generatedResetPassword.username}</code><br />
            <strong>New Temporary Password:</strong> <code>{generatedResetPassword.password}</code>
          </p>
          <button onClick={() => setGeneratedResetPassword(null)}>Dismiss</button>
        </section>
      )}

      <section className="card">
        <h2 id="password-resets-card">🔑 Pending Password Reset Requests</h2>
        <p className="note">
          Requests submitted via the public "Forgot Password" page. Approving generates a
          new temporary password for that user.
        </p>
        <table>
          <thead>
            <tr><th>User</th><th>Username</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {passwordResets.filter((r) => r.status === 'PENDING').map((r) => (
              <tr key={r.id}>
                <td>{r.full_name}</td>
                <td>{r.username}</td>
                <td><span className="badge badge-pending">Pending</span></td>
                <td>
                  <button onClick={() => handleApprovePasswordReset(r.id)}>Approve</button>
                  <button onClick={() => handleRejectPasswordReset(r.id)}>Reject</button>
                </td>
              </tr>
            ))}
            {passwordResets.filter((r) => r.status === 'PENDING').length === 0 && (
              <tr><td colSpan={4}>No pending requests.</td></tr>
            )}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2 id="institutions-card">🏢 Add New Institution</h2>
        <form onSubmit={handleCreateInstitution} className="upload-form">
          <label>Code (e.g. BANK-C)</label>
          <input value={newInstitution.code} onChange={(e) => setNewInstitution({ ...newInstitution, code: e.target.value })} required />
          <label>Institution Name</label>
          <input value={newInstitution.name} onChange={(e) => setNewInstitution({ ...newInstitution, name: e.target.value })} required />
          <label>Type</label>
          <select value={newInstitution.type} onChange={(e) => setNewInstitution({ ...newInstitution, type: e.target.value })}>
            <option value="BANK">Bank</option>
            <option value="METEOROLOGICAL_AUTHORITY">Meteorological Authority</option>
            <option value="GOVERNMENT_AGENCY">Government Agency</option>
            <option value="OTHER">Other</option>
          </select>
          <button type="submit">Add Institution</button>
        </form>
      </section>

      <section className="card">
        <h2 id="users-card">👤 Add New User</h2>
        <form onSubmit={handleCreateUser} className="upload-form">
          <label>Full Name</label>
          <input value={newUser.full_name} onChange={(e) => setNewUser({ ...newUser, full_name: e.target.value })} required />
          <label>Username</label>
          <input value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} required />
          <label>Email</label>
          <input type="email" value={newUser.email} onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} required />
          <label>Initial Password</label>
          <input type="password" value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} required />
          <label>Role</label>
          <select value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>
            <option value="INSTITUTION_USER">Institution User</option>
            <option value="BOT_USER">BOT User (Internal)</option>
            <option value="SYSTEM_ADMIN">System Admin</option>
          </select>
          <label>Institution (for Institution User)</label>
          <select value={newUser.institution_id} onChange={(e) => setNewUser({ ...newUser, institution_id: e.target.value })}>
            <option value="">-- None --</option>
            {institutions.map((i) => (
              <option key={i.id} value={i.id}>{i.name}</option>
            ))}
          </select>
          <button type="submit">Add User</button>
        </form>
      </section>

      <section className="card">
        <h2>👥 Users</h2>
        <table>
          <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.full_name}</td>
                <td>{u.username}</td>
                <td>{u.role}</td>
                <td>{u.is_active ? 'Active' : 'Deactivated'}</td>
                <td><button onClick={() => toggleUserActive(u)}>{u.is_active ? 'Deactivate' : 'Activate'}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2>🏢 Institutions</h2>
        <table>
          <thead><tr><th>Code</th><th>Name</th><th>Type</th><th>Status</th></tr></thead>
          <tbody>
            {institutions.map((i) => (
              <tr key={i.id}>
                <td>{i.code}</td>
                <td>{i.name}</td>
                <td>{i.type}</td>
                <td>{i.is_active ? 'Active' : 'Deactivated'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2>🧾 Audit Log</h2>
        <p className="note">System-wide record of important actions, for accountability and oversight.</p>
        <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', marginBottom: '0.5rem' }}>
          <input
            placeholder="Filter by action (e.g. LOGIN)"
            value={auditActionFilter}
            onChange={(e) => setAuditActionFilter(e.target.value)}
            style={{ maxWidth: 260 }}
          />
          <button onClick={() => loadAuditLogs(0)}>Apply Filter</button>
          <button onClick={handleExportAuditLog}>Export All (CSV)</button>
        </div>
        <table>
          <thead><tr><th>When</th><th>Action</th><th>Entity</th><th>Details</th></tr></thead>
          <tbody>
            {auditLogs.map((log) => (
              <tr key={log.id}>
                <td>{new Date(log.created_at).toLocaleString()}</td>
                <td>{log.action}</td>
                <td>{log.entity_type || '-'}</td>
                <td>{log.details || '-'}</td>
              </tr>
            ))}
            {auditLogs.length === 0 && <tr><td colSpan={4}>No audit entries yet.</td></tr>}
          </tbody>
        </table>
        {auditOffset + AUDIT_PAGE_SIZE < auditTotal && (
          <button onClick={() => loadAuditLogs(auditOffset + AUDIT_PAGE_SIZE)} style={{ marginTop: '0.75rem' }}>
            Load More ({auditLogs.length} of {auditTotal})
          </button>
        )}
      </section>
    </PortalShell>
  )
}
