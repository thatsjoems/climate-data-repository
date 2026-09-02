import { useState, FormEvent } from 'react'
import { Link } from 'react-router-dom'
import apiClient from '../api/client'

export default function ForgotPassword() {
  const [identifier, setIdentifier] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      await apiClient.post('/password-reset-requests', { username_or_email: identifier })
    } finally {
      setLoading(false)
      setSubmitted(true)
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>Forgot Password</h1>
        <p className="login-subtitle">
          Enter your username or work email. A System Administrator will review your
          request and share a new temporary password with you through a verified channel.
        </p>

        {submitted ? (
          <div className="alert-info">
            If an account matches what you entered, your request has been sent for review.
            You will be contacted with a new temporary password.
          </div>
        ) : (
          <>
            <label>Username or Email</label>
            <input
              required
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              autoFocus
            />
            <button type="submit" disabled={loading}>
              {loading ? 'Submitting...' : 'Request Password Reset'}
            </button>
          </>
        )}

        <div className="demo-hint">
          <Link to="/login">← Back to Log In</Link>
        </div>
      </form>
    </div>
  )
}
