import { useEffect, useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
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

interface AccessRequestItem {
  id: string
  institution_name: string
  institution_code: string | null
  institution_type: string
  contact_full_name: string
  contact_email: string
  contact_phone: string | null
  message: string | null
  status: string
  created_at: string
}

interface PasswordResetItem {
  id: string
  username: string
  full_name: string
  status: string
  created_at: string
}

export default function AdminPanel() {
  const navigate = useNavigate()
  const [users, setUsers] = useState<UserItem[]>([])
  const [institutions, setInstitutions] = useState<InstitutionItem[]>([])
  const [message, setMessage] = useState<string | null>(null)

  const [newUser, setNewUser] = useState({
    full_name: '', username: '', email: '', password: '', role: 'INSTITUTION_USER', institution_id: '',
  })
  const [newInstitution, setNewInstitution] = useState({ code: '', name: '', type: 'BANK' })
  const [accessRequests, setAccessRequests] = useState<AccessRequestItem[]>([])
  const [generatedCredential, setGeneratedCredential] = useState<{ username: string; password: string; emailSent: boolean } | null>(null)
  const [passwordResets, setPasswordResets] = useState<PasswordResetItem[]>([])
  const [generatedResetPassword, setGeneratedResetPassword] = useState<{ username: string; password: string; emailSent: boolean } | null>(null)

  async function loadAll() {
    const [usersRes, instRes, reqRes, resetRes] = await Promise.all([
      apiClient.get('/users'),
      apiClient.get('/institutions'),
      apiClient.get('/access-requests'),
      apiClient.get('/password-reset-requests'),
    ])
    setUsers(usersRes.data)
    setInstitutions(instRes.data)
    setAccessRequests(reqRes.data)
    setPasswordResets(resetRes.data)
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

  async function handleApproveRequest(id: string) {
    setMessage(null)
    try {
      const res = await apiClient.post(`/access-requests/${id}/approve`, {})
      setGeneratedCredential({
        username: res.data.generated_username,
        password: res.data.generated_temporary_password,
        emailSent: res.data.email_sent,
      })
      loadAll()
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || 'Failed to approve the request.')
    }
  }

  async function handleRejectRequest(id: string) {
    const notes = window.prompt('Reason for rejecting this request (optional):') || ''
    try {
      await apiClient.post(`/access-requests/${id}/reject`, { notes })
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
    { key: 'dashboard', icon: '📊', label: 'Back to Dashboard', onClick: () => navigate('/') },
    { key: 'requests', icon: '📨', label: 'Access Requests', active: true, onClick: () => scrollTo('access-requests-card') },
    { key: 'resets', icon: '🔑', label: 'Password Resets', onClick: () => scrollTo('password-resets-card') },
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

      {generatedCredential && (
        <section className="card" style={{ borderLeft: '3px solid var(--color-accent)' }}>
          <h2>✅ Account Created</h2>
          {generatedCredential.emailSent ? (
            <p>An email with these credentials was sent automatically to the institution's contact address.</p>
          ) : (
            <p>
              Email delivery is not configured in this environment — share these credentials
              with the institution through a verified channel (phone/official email) yourself.
            </p>
          )}
          <p>
            <strong>Username:</strong> <code>{generatedCredential.username}</code><br />
            <strong>Temporary Password:</strong> <code>{generatedCredential.password}</code>
          </p>
          <button onClick={() => setGeneratedCredential(null)}>Dismiss</button>
        </section>
      )}

      <section className="card">
        <h2 id="access-requests-card">📨 Pending Access Requests</h2>
        <p className="note">
          Institutions that used the public "Request Access" form. Approving a request
          creates the Institution (if new) and a user account with a temporary password.
        </p>
        <table>
          <thead>
            <tr><th>Institution</th><th>Contact</th><th>Email / Phone</th><th>Message</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {accessRequests.filter((r) => r.status === 'PENDING').map((r) => (
              <tr key={r.id}>
                <td>{r.institution_name}{r.institution_code ? ` (${r.institution_code})` : ''}</td>
                <td>{r.contact_full_name}</td>
                <td>{r.contact_email}{r.contact_phone ? ` / ${r.contact_phone}` : ''}</td>
                <td>{r.message || '-'}</td>
                <td><span className="badge badge-pending">Pending</span></td>
                <td>
                  <button onClick={() => handleApproveRequest(r.id)}>Approve</button>
                  <button onClick={() => handleRejectRequest(r.id)}>Reject</button>
                </td>
              </tr>
            ))}
            {accessRequests.filter((r) => r.status === 'PENDING').length === 0 && (
              <tr><td colSpan={6}>No pending requests.</td></tr>
            )}
          </tbody>
        </table>
      </section>

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
    </PortalShell>
  )
}
