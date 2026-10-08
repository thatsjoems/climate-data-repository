import { useState, FormEvent } from 'react'
import apiClient from '../api/client'
import { useAuth } from '../context/AuthContext'

// New recovery codes for someone who already uses two-step sign-in.
//
// The ten recovery codes are shown only once, when two-step sign-in is set up. Someone who did not save them had no way to get others. This card asks for
// the CURRENT 6-digit code (so a stolen session cannot do it), makes ten new codes, and the old ones stop working at that moment. The new ones are shown
// once, here, with the same Copy and Download buttons as at set-up.
export default function RecoveryCodesCard() {
  const { user } = useAuth()
  const [code, setCode] = useState('')
  const [codes, setCodes] = useState<string[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [saved, setSaved] = useState(false)

  // Nothing to show for someone who does not use two-step sign-in.
  if (!user?.mfa_enabled) return null

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res = await apiClient.post('/auth/mfa/recovery-codes', { code: code.replace(/\s+/g, '') })
      setCodes(res.data.recovery_codes)
      setSaved(false)
      setCode('')
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'New recovery codes could not be made. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  function copy(text: string) {
    navigator.clipboard?.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) }).catch(() => { /* the person can still select and copy the codes by hand */ })
  }

  function download(list: string[]) {
    const text = `Climate Data Repository - recovery codes for ${user?.username || ''}\n\nEach code works once. Keep this file somewhere safe, and not on the same computer as your sign-in details if you can.\n\n${list.join('\n')}\n`
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'cdr-recovery-codes.txt'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="card" style={{ marginTop: '1.25rem' }}>
      <h2 style={{ fontSize: '1.05rem', margin: '0 0 0.4rem' }}>Two-step sign-in: recovery codes</h2>

      {codes ? (
        <div>
          <div className="alert-info" style={{ fontSize: '0.85rem' }}>
            Your <strong>new recovery codes</strong> are below. They are shown only this once. <strong>The old codes no longer work.</strong> If you lose
            your authenticator, each code lets you in one time.
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.35rem', fontFamily: 'monospace', fontSize: '1rem', margin: '0.7rem 0' }}>
            {codes.map((c) => <div key={c}>{c}</div>)}
          </div>
          <p style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button type="button" className="btn-sm" onClick={() => copy(codes.join('\n'))}>{copied ? 'Copied' : 'Copy all'}</button>
            <button type="button" className="btn-sm" onClick={() => download(codes)}>Download as a file</button>
          </p>
          <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start', fontSize: '0.85rem' }}>
            <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} style={{ width: 'auto', marginTop: '0.2rem' }} />
            I have saved my new recovery codes somewhere safe.
          </label>
          <button type="button" disabled={!saved} style={{ marginTop: '0.8rem' }} onClick={() => { setCodes(null); setSaved(false) }}>Done</button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="upload-form" style={{ maxWidth: 'none' }}>
          <p className="note" style={{ margin: '0 0 0.6rem' }}>
            Lost or never saved your recovery codes? Make ten new ones. Type the 6-digit code your authenticator shows now. The old recovery codes stop
            working at once.
          </p>
          {error && <div className="alert-error">{error}</div>}
          <label htmlFor="recovery-current-code">Current 6-digit code</label>
          <input
            id="recovery-current-code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={12}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
          />
          <button type="submit" disabled={loading || code.replace(/\s+/g, '').length < 6} style={{ marginTop: '0.8rem', alignSelf: 'flex-start' }}>
            {loading ? 'Making codes...' : 'Make new recovery codes'}
          </button>
        </form>
      )}
    </section>
  )
}
