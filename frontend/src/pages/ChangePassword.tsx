import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import apiClient from '../api/client'
import { useAuth } from '../context/AuthContext'

interface Rule {
  label: string
  test: (pw: string) => boolean
}

const RULES: Rule[] = [
  { label: 'At least 8 characters', test: (pw) => pw.length >= 8 },
  { label: 'At least one letter', test: (pw) => /[A-Za-z]/.test(pw) },
  { label: 'At least one number', test: (pw) => /[0-9]/.test(pw) },
  { label: 'At least one special character (e.g. ! @ # $ %)', test: (pw) => /[^A-Za-z0-9]/.test(pw) },
]

export default function ChangePassword() {
  const { user, refreshUser } = useAuth()
  const navigate = useNavigate()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  const isForced = !!user?.must_change_password
  const allRulesMet = RULES.every((r) => r.test(newPassword))
  const passwordsMatch = newPassword.length > 0 && newPassword === confirmPassword

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    if (!allRulesMet) {
      setError('Your new password does not meet all the requirements below.')
      return
    }
    if (!passwordsMatch) {
      setError('The new password and confirmation do not match.')
      return
    }

    setLoading(true)
    try {
      await apiClient.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      await refreshUser()
      setSuccess(true)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      if (isForced) {
        setTimeout(() => navigate('/'), 1500)
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to change your password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page" style={{ maxWidth: 520 }}>
      <h1>🔒 Change Password</h1>
      {isForced ? (
        <div className="alert-error" style={{ marginBottom: '1rem' }}>
          You are using a temporary password. You must set your own password before you can
          continue to your dashboard.
        </div>
      ) : (
        <p className="note">
          Signed in as <strong>{user?.username}</strong>. Set your own password so you don't
          need to rely on a temporary one for future logins.
        </p>
      )}

      <section className="card">
        {success && (
          <div className="alert-info">
            Your password has been changed successfully.{isForced ? ' Redirecting you to your dashboard...' : ' Use your new password next time you log in.'}
          </div>
        )}
        {error && <div className="alert-error">{error}</div>}

        <form onSubmit={handleSubmit} className="upload-form" style={{ maxWidth: 'none' }}>
          <label>Current Password</label>
          <input
            type="password"
            required
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />

          <label>New Password</label>
          <input
            type="password"
            required
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />

          <label>Confirm New Password</label>
          <input
            type="password"
            required
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />

          <div style={{ marginTop: '0.9rem' }}>
            {RULES.map((r) => {
              const met = r.test(newPassword)
              return (
                <div key={r.label} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem', color: met ? '#0B7D62' : 'var(--color-muted)', marginBottom: '0.25rem' }}>
                  <span>{met ? '✅' : '⬜'}</span>
                  <span>{r.label}</span>
                </div>
              )
            })}
            {confirmPassword.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem', color: passwordsMatch ? '#0B7D62' : 'var(--color-muted)' }}>
                <span>{passwordsMatch ? '✅' : '⬜'}</span>
                <span>Passwords match</span>
              </div>
            )}
          </div>

          <button type="submit" disabled={loading} style={{ marginTop: '1rem', alignSelf: 'flex-start' }}>
            {loading ? 'Saving...' : 'Change Password'}
          </button>
        </form>
      </section>

      {!isForced && (
        <button onClick={() => navigate(-1)} style={{ background: 'transparent', color: 'var(--color-primary)', border: 'none', padding: 0, cursor: 'pointer', fontSize: '0.85rem' }}>
          ← Back to Dashboard
        </button>
      )}
    </div>
  )
}
