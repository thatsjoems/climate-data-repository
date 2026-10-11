import { useState, FormEvent, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import apiClient from '../api/client'
import botLogo from '../assets/bot_logo.png'
import { CodeStep, SetupStep } from './TwoStepSignIn'
import type { Portal } from '../portal'

/**
 * One sign-in form, two doors. Bank staff (BOT analysts, System Administrators) use /staff/login; reporting institutions use /login.
 * The page tells the server which door it is, and the server turns away anyone who belongs to the other one.
 */
const WORDS: Record<Portal, { title: string; subtitle: string; badge: string | null; notice: string; button: string }> = {
  internal: {
    title: 'Climate Data Repository',
    subtitle: 'Bank of Tanzania - Staff sign-in',
    badge: 'Bank staff only',
    notice: 'This page is for Bank of Tanzania staff (analysts and system administrators). Two-step verification applies. '
      + 'All activities are monitored and recorded.',
    button: 'Staff Log In',
  },
  external: {
    title: 'Climate Data Repository',
    subtitle: 'Reporting institutions portal',
    badge: null,
    notice: 'This portal is for authorized users of reporting financial institutions. All activities are monitored and recorded.',
    button: 'Log In',
  },
}

export default function SignInForm({ portal }: { portal: Portal }) {
  const words = WORDS[portal]
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const { login, isLoading, error } = useAuth()
  // After the password the server may ask for a second step (the code, or first-time set-up): the page then shows that step.
  const [step, setStep] = useState<{ mode: 'code' | 'setup'; mfaToken: string } | null>(null)
  const navigate = useNavigate()
  // Demo credentials must never be advertised in production (item 7 of the September 2026 external review): they are shown only
  // once /api/health confirms the environment is not production, and hidden until then.
  const [showDemoHint, setShowDemoHint] = useState(false)

  useEffect(() => {
    apiClient.get('/health')
      .then((res) => setShowDemoHint(res.data?.environment !== 'production'))
      .catch(() => setShowDemoHint(false))
  }, [])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    try {
      const result = await login(username, password, portal)
      if (result.status === 'done') navigate('/')
      else setStep({ mode: result.status, mfaToken: result.mfaToken })
    } catch {
      // error is already surfaced via AuthContext
    }
  }

  const brand = (
    <div className="login-brand">
      <img src={botLogo} alt="Bank of Tanzania" className="login-logo" />
      <h1>{words.title}</h1>
      <p className="login-subtitle">{words.subtitle}</p>
      {words.badge && <span className="login-badge" data-testid="login-badge">{words.badge}</span>}
    </div>
  )
  const pageClass = `login-page login-page--${portal}`

  if (step) {
    const common = { mfaToken: step.mfaToken, onDone: () => navigate('/'), onBack: () => { setStep(null); setPassword('') } }
    return (
      <div className={pageClass} data-portal={portal}>
        <div className="login-card">
          {brand}
          {step.mode === 'code' ? <CodeStep {...common} /> : <SetupStep {...common} />}
        </div>
      </div>
    )
  }

  return (
    <div className={pageClass} data-portal={portal}>
      <form className="login-card" onSubmit={handleSubmit}>
        {brand}

        {error && <div className="alert-error" role="alert">{error}</div>}

        <label htmlFor="signin-username">Username</label>
        <input id="signin-username" type="text" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />

        <label htmlFor="signin-password">Password</label>
        <input id="signin-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <p style={{ textAlign: 'right', margin: '0.35rem 0 0' }}>
          <Link to="/forgot-password" style={{ fontSize: '0.78rem', color: 'var(--color-muted)' }}>Forgot password?</Link>
        </p>

        <button type="submit" disabled={isLoading} className="login-submit">
          {isLoading ? 'Signing in...' : words.button}
        </button>

        <div className="login-notice">
          <strong>🛡️ Authorized Access Only</strong>
          <p>{words.notice}</p>
        </div>

        {showDemoHint && (
          <div className="demo-hint">
            <strong>DEMO accounts (after running init_db.py):</strong>
            <ul>
              {portal === 'internal' ? (
                <>
                  <li>Admin: <code>admin</code> / <code>Admin@123</code></li>
                  <li>BOT Analyst: <code>bot_analyst</code> / <code>Analyst@123</code></li>
                </>
              ) : (
                <li>Institution (Bank A): <code>bankA_user</code> / <code>BankA@123</code></li>
              )}
            </ul>
            <p style={{ marginTop: '0.5rem', fontSize: '0.72rem' }}>
              ⚠️ Climate observations in this environment are <strong>SYNTHETIC demo data</strong> —
              not official TMA readings. See the "Climate Data Quality" section on the Analyst
              dashboard for exactly which records are synthetic vs validated.
            </p>
          </div>
        )}

        <p className="login-footer">© 2026 Bank of Tanzania. All rights reserved.</p>
      </form>
    </div>
  )
}
