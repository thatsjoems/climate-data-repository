import { useEffect, useState, FormEvent } from 'react'
import apiClient from '../api/client'

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

export default function AdminPanel() {
  const [users, setUsers] = useState<UserItem[]>([])
  const [institutions, setInstitutions] = useState<InstitutionItem[]>([])
  const [message, setMessage] = useState<string | null>(null)

  const [newUser, setNewUser] = useState({
    full_name: '', username: '', email: '', password: '', role: 'INSTITUTION_USER', institution_id: '',
  })
  const [newInstitution, setNewInstitution] = useState({ code: '', name: '', type: 'BANK' })

  async function loadAll() {
    const [usersRes, instRes] = await Promise.all([
      apiClient.get('/users'),
      apiClient.get('/institutions'),
    ])
    setUsers(usersRes.data)
    setInstitutions(instRes.data)
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
      setMessage('Mtumiaji ameongezwa kikamilifu.')
      setNewUser({ full_name: '', username: '', email: '', password: '', role: 'INSTITUTION_USER', institution_id: '' })
      loadAll()
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || 'Imeshindikana kuongeza mtumiaji.')
    }
  }

  async function handleCreateInstitution(e: FormEvent) {
    e.preventDefault()
    setMessage(null)
    try {
      await apiClient.post('/institutions', newInstitution)
      setMessage('Taasisi imeongezwa kikamilifu.')
      setNewInstitution({ code: '', name: '', type: 'BANK' })
      loadAll()
    } catch (err: any) {
      setMessage(err?.response?.data?.detail || 'Imeshindikana kuongeza taasisi.')
    }
  }

  async function toggleUserActive(u: UserItem) {
    const action = u.is_active ? 'deactivate' : 'activate'
    await apiClient.patch(`/users/${u.id}/${action}`)
    loadAll()
  }

  return (
    <div className="page">
      <h1>Usimamizi wa Mfumo (Administration)</h1>
      {message && <div className="alert-info">{message}</div>}

      <section className="card">
        <h2>Ongeza Taasisi Mpya</h2>
        <form onSubmit={handleCreateInstitution} className="upload-form">
          <label>Code (mfano BANK-C)</label>
          <input value={newInstitution.code} onChange={(e) => setNewInstitution({ ...newInstitution, code: e.target.value })} required />
          <label>Jina la Taasisi</label>
          <input value={newInstitution.name} onChange={(e) => setNewInstitution({ ...newInstitution, name: e.target.value })} required />
          <label>Aina</label>
          <select value={newInstitution.type} onChange={(e) => setNewInstitution({ ...newInstitution, type: e.target.value })}>
            <option value="BANK">Benki</option>
            <option value="METEOROLOGICAL_AUTHORITY">Mamlaka ya Hali ya Hewa</option>
            <option value="GOVERNMENT_AGENCY">Taasisi ya Serikali</option>
            <option value="OTHER">Nyingine</option>
          </select>
          <button type="submit">Ongeza Taasisi</button>
        </form>
      </section>

      <section className="card">
        <h2>Ongeza Mtumiaji Mpya</h2>
        <form onSubmit={handleCreateUser} className="upload-form">
          <label>Jina Kamili</label>
          <input value={newUser.full_name} onChange={(e) => setNewUser({ ...newUser, full_name: e.target.value })} required />
          <label>Username</label>
          <input value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} required />
          <label>Email</label>
          <input type="email" value={newUser.email} onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} required />
          <label>Password ya Awali</label>
          <input type="password" value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} required />
          <label>Role</label>
          <select value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>
            <option value="INSTITUTION_USER">Institution User</option>
            <option value="BOT_USER">BOT User (Internal)</option>
            <option value="SYSTEM_ADMIN">System Admin</option>
          </select>
          <label>Taasisi (kwa Institution User)</label>
          <select value={newUser.institution_id} onChange={(e) => setNewUser({ ...newUser, institution_id: e.target.value })}>
            <option value="">-- Hakuna --</option>
            {institutions.map((i) => (
              <option key={i.id} value={i.id}>{i.name}</option>
            ))}
          </select>
          <button type="submit">Ongeza Mtumiaji</button>
        </form>
      </section>

      <section className="card">
        <h2>Orodha ya Watumiaji</h2>
        <table>
          <thead><tr><th>Jina</th><th>Username</th><th>Role</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.full_name}</td>
                <td>{u.username}</td>
                <td>{u.role}</td>
                <td>{u.is_active ? 'Active' : 'Deactivated'}</td>
                <td><button onClick={() => toggleUserActive(u)}>{u.is_active ? 'Zima' : 'Washa'}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2>Orodha ya Taasisi</h2>
        <table>
          <thead><tr><th>Code</th><th>Jina</th><th>Aina</th><th>Status</th></tr></thead>
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
    </div>
  )
}
