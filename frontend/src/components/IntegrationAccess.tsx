import { useEffect, useState } from 'react'
import { apiClient } from '../api/client'

interface ApiClientItem {
  id: string
  name: string
  description: string | null
  key_prefix: string
  scope: 'READ' | 'INGEST_TMA' | 'INGEST_PMO'
  allowed_networks: string | null
  status: 'ACTIVE' | 'EXPIRED' | 'REVOKED'
  created_by_username: string | null
  revoked_by_username: string | null
  created_at: string
  expires_at: string
  last_used_at: string | null
  revoked_at: string | null
}

interface CreatedKey extends ApiClientItem {
  api_key: string
}

const STATUS_COLOR: Record<string, string> = { ACTIVE: '#14702F', EXPIRED: '#8a6d00', REVOKED: '#b42318' }

const SCOPE_LABEL: Record<string, string> = {
  READ: 'Read approved data',
  INGEST_TMA: 'Send TMA climate files',
  INGEST_PMO: 'Send PMO climate files',
}

function when(value: string | null): string {
  return value ? new Date(value).toLocaleString() : 'never'
}

// The server answers a validation problem with a list, not a sentence: only show text we can read.
function errorText(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

/**
 * Read-only keys for external systems (QGIS, ArcGIS, TMA, BSIS, RTIS). A BOT analyst creates them (canCreate);
 * the System Administrator can only list and revoke them. The key is shown once, at creation, and never again.
 */
export default function IntegrationAccess({ canCreate }: { canCreate: boolean }) {
  const [clients, setClients] = useState<ApiClientItem[]>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [validDays, setValidDays] = useState('180')
  const [scope, setScope] = useState('READ')
  const [allowed, setAllowed] = useState('')
  const [created, setCreated] = useState<CreatedKey | null>(null)
  const [copied, setCopied] = useState(false)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)

  async function load() {
    const res = await apiClient.get('/integration-clients')
    setClients(res.data)
  }

  useEffect(() => {
    load().catch((err: any) => setMessage(errorText(err, 'Could not load the keys.')))
  }, [])

  async function createKey() {
    setMessage('')
    const days = parseInt(validDays, 10)
    if (!name.trim()) {
      setMessage('Give the key a name that says which system it is for.')
      return
    }
    if (!(days >= 1 && days <= 365)) {
      setMessage('A key must last between 1 and 365 days.')
      return
    }
    setBusy(true)
    try {
      const res = await apiClient.post('/integration-clients', {
        name: name.trim(), description: description.trim() || null, valid_days: days, scope, allowed_networks: allowed.trim() || null,
      })
      setCreated(res.data)
      setCopied(false)
      setName('')
      setDescription('')
      setValidDays('180')
      setAllowed('')
      setScope('READ')
      await load()
    } catch (err: any) {
      setMessage(errorText(err, 'Could not create the key.'))
    } finally {
      setBusy(false)
    }
  }

  async function revoke(item: ApiClientItem) {
    if (!window.confirm(`Revoke the key "${item.name}"? Whatever uses it stops working at once. This cannot be undone.`)) return
    setMessage('')
    try {
      await apiClient.post(`/integration-clients/${item.id}/revoke`)
      await load()
    } catch (err: any) {
      setMessage(errorText(err, 'Could not revoke the key.'))
    }
  }

  async function copyKey() {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.api_key)
      setCopied(true)
    } catch (err: any) {
      setMessage('Copying failed. Select the key and copy it by hand.')
    }
  }

  const labelStyle = { display: 'flex', flexDirection: 'column' as const, gap: '0.2rem', fontSize: '0.78rem' }

  return (
    <section className="card" id="integration-section">
      <h2>🔌 Integration Access (read-only keys)</h2>
      <p className="note">
        A key lets an external system either read the approved figures exactly as the dashboard shows them (QGIS, ArcGIS, BSIS,
        RTIS), or send climate files (TMA, PMO), never both. Files it sends are stored as UNVALIDATED until a BOT analyst promotes
        them. A key expires, and every use is written to the audit log.{' '}
        {canCreate
          ? 'The key is shown once, when you create it: keep it in a secret store, never in an e-mail or a chat.'
          : 'You can list and revoke keys; only a BOT analyst can create one.'}
      </p>
      {message && <p style={{ color: '#b42318' }}>{message}</p>}

      {created && (
        <div style={{ border: '2px solid #C9A227', background: '#fffbe6', borderRadius: 6, padding: '0.75rem', margin: '0.75rem 0' }}>
          <strong>Copy this key now. It is shown only once.</strong>
          <code style={{ display: 'block', wordBreak: 'break-all', margin: '0.5rem 0', padding: '0.5rem', background: '#fff', border: '1px solid #ddd' }}>
            {created.api_key}
          </code>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button className="btn-secondary btn-sm" onClick={copyKey}>{copied ? 'Copied' : 'Copy key'}</button>
            <button className="btn-secondary btn-sm" onClick={() => setCreated(null)}>I have saved it</button>
          </div>
          <p className="note" style={{ marginBottom: 0 }}>
            Key for "{created.name}", valid until {when(created.expires_at)}. Send it in the header X-API-Key (or as a Bearer token) to /api/integration/{created.scope === 'READ' ? '...' : 'climate-data'}.
          </p>
        </div>
      )}

      {canCreate && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end', margin: '0.75rem 0' }}>
          <label style={labelStyle}>
            Name (which system)
            <input value={name} maxLength={120} placeholder="e.g. QGIS - FSD GIS desk" onChange={(e) => setName(e.target.value)} style={{ minWidth: 240 }} />
          </label>
          <label style={labelStyle}>
            Description (optional)
            <input value={description} maxLength={500} onChange={(e) => setDescription(e.target.value)} style={{ minWidth: 240 }} />
          </label>
          <label style={labelStyle}>
            What it may do
            <select value={scope} onChange={(e) => setScope(e.target.value)} style={{ minWidth: 200 }}>
              <option value="READ">{SCOPE_LABEL.READ}</option>
              <option value="INGEST_TMA">{SCOPE_LABEL.INGEST_TMA}</option>
              <option value="INGEST_PMO">{SCOPE_LABEL.INGEST_PMO}</option>
            </select>
          </label>
          <label style={labelStyle}>
            Valid for (days, 1 to 365)
            <input value={validDays} inputMode="numeric" onChange={(e) => setValidDays(e.target.value)} style={{ width: 90 }} />
          </label>
          <label style={labelStyle}>
            Allowed from (optional addresses or networks)
            <input value={allowed} maxLength={500} placeholder="e.g. 203.0.113.7, 10.20.0.0/16" onChange={(e) => setAllowed(e.target.value)} style={{ minWidth: 230 }} />
          </label>
          <button onClick={createKey} disabled={busy}>{busy ? 'Creating...' : 'Create key'}</button>
        </div>
      )}

      <table>
        <thead>
          <tr><th>Name</th><th>Key</th><th>May do</th><th>Status</th><th>Created by</th><th>Allowed from</th><th>Expires</th><th>Last used</th><th></th></tr>
        </thead>
        <tbody>
          {clients.length === 0 && <tr><td colSpan={9}>No keys yet.</td></tr>}
          {clients.map((c) => (
            <tr key={c.id}>
              <td>{c.name}{c.description ? <div className="note" style={{ margin: 0 }}>{c.description}</div> : null}</td>
              <td><code>cdrk_{c.key_prefix}_...</code></td>
              <td>{SCOPE_LABEL[c.scope] || c.scope}</td>
              <td style={{ color: STATUS_COLOR[c.status] || 'inherit', fontWeight: 600 }}>{c.status}</td>
              <td>{c.created_by_username || '-'}</td>
              <td>{c.allowed_networks || 'any address'}</td>
              <td>{when(c.expires_at)}</td>
              <td>{when(c.last_used_at)}</td>
              <td>{c.status === 'ACTIVE' && <button className="btn-secondary btn-sm" onClick={() => revoke(c)}>Revoke</button>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
