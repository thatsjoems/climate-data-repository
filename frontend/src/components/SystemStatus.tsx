import { useEffect, useState } from 'react'
import { apiClient } from '../api/client'

type Level = 'OK' | 'INFO' | 'WARN' | 'CRITICAL'

interface CheckItem {
  key: string
  title: string
  status: Level
  message: string
  details: Record<string, any>
}

interface StatusData {
  generated_at: string
  overall: 'OK' | 'WARN' | 'CRITICAL'
  counts: Record<string, number>
  checks: CheckItem[]
  monitoring_interval_minutes: number
}

const COLOUR: Record<Level, string> = { OK: '#1a7f37', INFO: '#57606a', WARN: '#b26a00', CRITICAL: '#b42318' }
const WORD: Record<Level, string> = { OK: 'OK', INFO: 'Info', WARN: 'Attention', CRITICAL: 'Urgent' }

function Badge({ level }: { level: Level }) {
  return (
    <span style={{ background: COLOUR[level], color: '#fff', borderRadius: 4, padding: '0.1rem 0.5rem', fontSize: '0.72rem', fontWeight: 600, whiteSpace: 'nowrap' }}>
      {WORD[level]}
    </span>
  )
}

function show(value: any): string {
  return value !== null && typeof value === 'object' ? JSON.stringify(value) : String(value)
}

// What the system checks on itself (database, schema, backups, disk, failed sign-ins, keys, administrators), refreshed every minute.
// The same checks raise notifications for System Administrators when the background monitor is on (see docs/MONITORING.md).
export default function SystemStatus() {
  const [data, setData] = useState<StatusData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const res = await apiClient.get('/system/status')
      setData(res.data)
      setError(null)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Could not read the system status.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 60000)
    return () => clearInterval(timer)
  }, [])

  const worst: Level = data ? data.overall : 'INFO'
  const headline = !data ? 'Checking...' : data.overall === 'OK' ? 'Everything is working' : data.overall === 'WARN' ? 'Something needs attention' : 'Something is wrong'

  return (
    <section className="card" id="status-section" style={{ borderLeft: `4px solid ${COLOUR[worst]}` }}>
      <h2>📊 System Status</h2>
      {error && <div className="alert-error">{error}</div>}
      {data && (
        <>
          <p style={{ margin: '0 0 0.6rem' }}>
            <Badge level={data.overall} /> <strong style={{ marginLeft: '0.4rem' }}>{headline}</strong>
            <span style={{ marginLeft: '0.8rem', fontSize: '0.78rem', color: 'var(--color-muted)' }}>
              checked {new Date(data.generated_at + 'Z').toLocaleTimeString()} ·{' '}
              {data.monitoring_interval_minutes > 0
                ? `alerts reach you in the bell every ${data.monitoring_interval_minutes} minutes`
                : 'background alerts are off in this environment'}
            </span>{' '}
            <button className="btn-sm" onClick={load} disabled={loading}>{loading ? 'Checking...' : 'Check now'}</button>
          </p>
          <table>
            <thead><tr><th style={{ width: '7rem' }}>Status</th><th style={{ width: '12rem' }}>Check</th><th>What it found</th></tr></thead>
            <tbody>
              {data.checks.map((c) => (
                <tr key={c.key}>
                  <td><Badge level={c.status} /></td>
                  <td><strong>{c.title}</strong></td>
                  <td>
                    {c.message}
                    {Object.keys(c.details).length > 0 && (
                      <details style={{ marginTop: '0.25rem' }}>
                        <summary style={{ fontSize: '0.75rem', cursor: 'pointer' }}>Details</summary>
                        <dl style={{ fontSize: '0.75rem', margin: '0.3rem 0 0' }}>
                          {Object.entries(c.details).map(([k, v]) => (
                            <div key={k}><dt style={{ display: 'inline', fontWeight: 600 }}>{k.replace(/_/g, ' ')}: </dt><dd style={{ display: 'inline', margin: 0 }}>{show(v)}</dd></div>
                          ))}
                        </dl>
                      </details>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  )
}
