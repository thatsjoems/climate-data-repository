import { useState, FormEvent } from 'react'
import { Link } from 'react-router-dom'
import apiClient from '../api/client'

export default function RequestAccess() {
  const [form, setForm] = useState({
    institution_name: '',
    institution_code: '',
    institution_type: 'BANK',
    contact_full_name: '',
    contact_email: '',
    contact_phone: '',
    message: '',
  })
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await apiClient.post('/access-requests', {
        ...form,
        institution_code: form.institution_code || null,
      })
      setSubmitted(true)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to submit the request. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" style={{ maxWidth: 460 }} onSubmit={handleSubmit}>
        <h1>Request Access</h1>
        <p className="login-subtitle">
          For institutions that need to report climate-related financial data to the
          Bank of Tanzania. Submitting this form does <strong>not</strong> create a login —
          a System Administrator will review your request and, once your institution is
          verified, will provision an account for you.
        </p>

        {submitted ? (
          <div className="alert-info">
            Your request has been submitted. A Bank of Tanzania System Administrator will
            review it and contact you at the email/phone you provided once your account is
            ready.
          </div>
        ) : (
          <>
            {error && <div className="alert-error">{error}</div>}

            <label>Institution Name</label>
            <input
              required
              value={form.institution_name}
              onChange={(e) => setForm({ ...form, institution_name: e.target.value })}
            />

            <label>Institution Type</label>
            <select
              value={form.institution_type}
              onChange={(e) => setForm({ ...form, institution_type: e.target.value })}
            >
              <option value="BANK">Bank</option>
              <option value="METEOROLOGICAL_AUTHORITY">Meteorological Authority</option>
              <option value="GOVERNMENT_AGENCY">Government Agency</option>
              <option value="OTHER">Other</option>
            </select>

            <label>Institution Code (if already known/assigned)</label>
            <input
              value={form.institution_code}
              onChange={(e) => setForm({ ...form, institution_code: e.target.value })}
              placeholder="Optional"
            />

            <label>Your Full Name</label>
            <input
              required
              value={form.contact_full_name}
              onChange={(e) => setForm({ ...form, contact_full_name: e.target.value })}
            />

            <label>Your Work Email</label>
            <input
              required
              type="email"
              value={form.contact_email}
              onChange={(e) => setForm({ ...form, contact_email: e.target.value })}
            />

            <label>Phone Number</label>
            <input
              value={form.contact_phone}
              onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
              placeholder="Optional"
            />

            <label>Message (optional)</label>
            <input
              value={form.message}
              onChange={(e) => setForm({ ...form, message: e.target.value })}
              placeholder="Anything the reviewer should know"
            />

            <button type="submit" disabled={loading}>
              {loading ? 'Submitting...' : 'Submit Request'}
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
