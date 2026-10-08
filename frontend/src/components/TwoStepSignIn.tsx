import { useEffect, useState, FormEvent } from 'react'
import { useAuth, SetupInfo, PendingSession } from '../context/AuthContext'

interface StepProps {
  mfaToken: string
  onDone: () => void
  onBack: () => void
}

function messageOf(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

// ---------------------------------------------------------------- the second step: the code from the authenticator app
export function CodeStep({ mfaToken, onDone, onBack }: StepProps) {
  const { verifyCode } = useAuth()
  const [useRecovery, setUseRecovery] = useState(false)
  const [entry, setEntry] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await verifyCode(mfaToken, useRecovery ? { recoveryCode: entry } : { code: entry })
      onDone()
    } catch (err: any) {
      setError(messageOf(err, 'Could not check the code. Please try again.'))
      setEntry('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit}>
      <h2 style={{ fontSize: '1.05rem', margin: '0 0 0.4rem' }}>Two-step sign-in</h2>
      <p style={{ fontSize: '0.85rem', margin: '0 0 0.6rem' }}>
        {useRecovery
          ? 'Enter one of your recovery codes. Each one works only once.'
          : 'Open your authenticator app and enter the 6-digit code for Climate Data Repository.'}
      </p>
      {error && <div className="alert-error">{error}</div>}
      <label>{useRecovery ? 'Recovery code' : '6-digit code'}</label>
      <input
        type="text"
        value={entry}
        onChange={(e) => setEntry(e.target.value)}
        inputMode={useRecovery ? 'text' : 'numeric'}
        autoComplete="one-time-code"
        maxLength={useRecovery ? 16 : 7}
        placeholder={useRecovery ? 'XXXXX-XXXXX' : '123456'}
        required
        autoFocus
        style={{ letterSpacing: useRecovery ? '0.08em' : '0.3em', fontFamily: 'monospace' }}
      />
      <button type="submit" disabled={busy || !entry.trim()} className="login-submit">{busy ? 'Checking...' : 'Continue'}</button>
      <p style={{ fontSize: '0.8rem', marginTop: '0.7rem' }}>
        <a href="#" onClick={(e) => { e.preventDefault(); setUseRecovery(!useRecovery); setEntry(''); setError(null) }}>
          {useRecovery ? 'Use the code from my app instead' : 'I lost my phone: use a recovery code'}
        </a>
        {' · '}
        <a href="#" onClick={(e) => { e.preventDefault(); onBack() }}>Back to sign in</a>
      </p>
    </form>
  )
}

// ---------------------------------------------------------------- first time: set up the authenticator app, then keep the recovery codes
export function SetupStep({ mfaToken, onDone, onBack }: StepProps) {
  const { beginMfaSetup, confirmMfaSetup } = useAuth()
  const [info, setInfo] = useState<SetupInfo | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState<PendingSession | null>(null)
  const [saved, setSaved] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let alive = true
    beginMfaSetup(mfaToken)
      .then((data) => { if (alive) setInfo(data) })
      .catch((err) => { if (alive) setError(messageOf(err, 'Could not start the set-up. Please sign in again.')) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mfaToken])

  async function confirm(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      setPending(await confirmMfaSetup(mfaToken, code))
    } catch (err: any) {
      setError(messageOf(err, 'Could not check the code. Please try again.'))
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  function copy(text: string) {
    navigator.clipboard?.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) }).catch(() => { /* the key is on screen to type */ })
  }

  function download(codes: string[]) {
    const text = `Climate Data Repository - recovery codes for ${info?.account || ''}\n\nEach code works once. Keep this file somewhere safe and private.\n\n${codes.join('\n')}\n`
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'cdr-recovery-codes.txt'
    a.click()
    URL.revokeObjectURL(url)
  }

  // ---- after the code was right: the recovery codes, shown once
  if (pending) {
    return (
      <div>
        <h2 style={{ fontSize: '1.05rem', margin: '0 0 0.4rem' }}>Two-step sign-in is on</h2>
        <div className="alert-info" style={{ fontSize: '0.85rem' }}>
          Save these <strong>recovery codes</strong> now. They are shown only this once. If you lose your phone, each code lets you in one time.
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.35rem', fontFamily: 'monospace', fontSize: '1rem', margin: '0.7rem 0' }}>
          {pending.recoveryCodes.map((c) => <div key={c}>{c}</div>)}
        </div>
        <p style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button type="button" className="btn-sm" onClick={() => copy(pending.recoveryCodes.join('\n'))}>{copied ? 'Copied' : 'Copy all'}</button>
          <button type="button" className="btn-sm" onClick={() => download(pending.recoveryCodes)}>Download as a file</button>
        </p>
        <label style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start', fontSize: '0.85rem' }}>
          <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} style={{ width: 'auto', marginTop: '0.2rem' }} />
          I have saved my recovery codes somewhere safe.
        </label>
        <button type="button" className="login-submit" disabled={!saved} onClick={() => { pending.finish(); onDone() }}>Continue to the portal</button>
      </div>
    )
  }

  // ---- add the account to the authenticator app, then prove it works with its first code
  const spaced = info ? (info.secret.match(/.{1,4}/g) || []).join(' ') : ''
  return (
    <form onSubmit={confirm}>
      <h2 style={{ fontSize: '1.05rem', margin: '0 0 0.4rem' }}>Set up two-step sign-in</h2>
      <p style={{ fontSize: '0.85rem', margin: '0 0 0.6rem' }}>
        The Bank requires a second step for staff accounts. You need an authenticator app on your phone, for example Google Authenticator,
        Microsoft Authenticator or FreeOTP.
      </p>
      {error && <div className="alert-error">{error}</div>}
      {!info && !error && <p>Preparing...</p>}
      {info && (
        <>
          <ol style={{ fontSize: '0.85rem', paddingLeft: '1.1rem', margin: '0 0 0.6rem' }}>
            <li>In the app, add an account: scan this picture, or choose &quot;enter a setup key&quot;.</li>
            <li>Then type the 6-digit code the app shows.</li>
          </ol>
          {info.qr_svg && (
            <p style={{ textAlign: 'center', margin: '0.3rem 0' }}>
              <img
                alt="QR code for the authenticator app"
                width={190}
                height={190}
                src={`data:image/svg+xml;utf8,${encodeURIComponent(info.qr_svg)}`}
                style={{ background: '#fff', border: '1px solid #ddd' }}
              />
            </p>
          )}
          <p style={{ fontSize: '0.8rem', margin: '0.3rem 0' }}>
            Setup key (account <strong>{info.account}</strong>, time based):<br />
            <code style={{ fontSize: '0.95rem', letterSpacing: '0.05em', wordBreak: 'break-all' }}>{spaced}</code>{' '}
            <button type="button" className="btn-sm" onClick={() => copy(info.secret)}>{copied ? 'Copied' : 'Copy'}</button>
          </p>
          <label>6-digit code from the app</label>
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={7}
            placeholder="123456"
            required
            autoFocus
            style={{ letterSpacing: '0.3em', fontFamily: 'monospace' }}
          />
          <button type="submit" disabled={busy || !code.trim()} className="login-submit">{busy ? 'Checking...' : 'Turn on and sign in'}</button>
        </>
      )}
      <p style={{ fontSize: '0.8rem', marginTop: '0.7rem' }}><a href="#" onClick={(e) => { e.preventDefault(); onBack() }}>Back to sign in</a></p>
    </form>
  )
}
