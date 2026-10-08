import { createContext, useContext, useState, ReactNode } from 'react'
import apiClient from '../api/client'

export interface CurrentUser {
  id: string
  full_name: string
  username: string
  email: string
  role: 'SYSTEM_ADMIN' | 'BOT_USER' | 'INSTITUTION_USER'
  institution_id: string | null
  must_change_password: boolean
  mfa_enabled?: boolean
}

// Signing in has up to two steps. After the password the server either signs the person in ('done') or asks for the 6-digit code
// ('code'), or, for the Bank's staff who have not set up two-step sign-in yet, asks them to set it up ('setup').
export type SignInResult =
  | { status: 'done' }
  | { status: 'code'; mfaToken: string }
  | { status: 'setup'; mfaToken: string }

export interface SetupInfo {
  secret: string
  otpauth_uri: string
  issuer: string
  account: string
  qr_svg: string | null
}

// Set-up ends with the recovery codes, which are shown ONCE. The session is held back until the person has seen them (finish()),
// so the page does not move on before they are saved.
export interface PendingSession {
  recoveryCodes: string[]
  finish: () => void
}

interface AuthContextType {
  user: CurrentUser | null
  login: (username: string, password: string) => Promise<SignInResult>
  verifyCode: (mfaToken: string, entry: { code?: string; recoveryCode?: string }) => Promise<void>
  beginMfaSetup: (mfaToken: string) => Promise<SetupInfo>
  confirmMfaSetup: (mfaToken: string, code: string) => Promise<PendingSession>
  logout: () => void
  refreshUser: () => Promise<void>
  isLoading: boolean
  error: string | null
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(() => {
    const stored = localStorage.getItem('cdr_user')
    return stored ? JSON.parse(stored) : null
  })
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function commitSession(data: any) {
    localStorage.setItem('cdr_token', data.access_token)
    localStorage.setItem('cdr_refresh_token', data.refresh_token)
    localStorage.setItem('cdr_user', JSON.stringify(data.user))
    setUser(data.user)
  }

  async function login(username: string, password: string): Promise<SignInResult> {
    setIsLoading(true)
    setError(null)
    try {
      const res = await apiClient.post('/auth/login', { username, password })
      if (res.data.access_token) {
        commitSession(res.data)
        return { status: 'done' }
      }
      if (res.data.mfa_required && res.data.mfa_token) return { status: 'code', mfaToken: res.data.mfa_token }
      if (res.data.mfa_setup_required && res.data.mfa_token) return { status: 'setup', mfaToken: res.data.mfa_token }
      throw new Error('Unexpected answer from the server')
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Login failed. Please try again.'
      setError(typeof msg === 'string' ? msg : 'Login failed. Please try again.')
      throw err
    } finally {
      setIsLoading(false)
    }
  }

  // The second step: the 6-digit code from the authenticator app, or one recovery code. Errors are shown by the step itself.
  async function verifyCode(mfaToken: string, entry: { code?: string; recoveryCode?: string }) {
    const body = entry.recoveryCode
      ? { mfa_token: mfaToken, recovery_code: entry.recoveryCode.trim() }
      : { mfa_token: mfaToken, code: (entry.code || '').trim() }
    const res = await apiClient.post('/auth/mfa/verify', body)
    commitSession(res.data)
  }

  async function beginMfaSetup(mfaToken: string): Promise<SetupInfo> {
    const res = await apiClient.post('/auth/mfa/setup/begin', { mfa_token: mfaToken })
    return res.data
  }

  async function confirmMfaSetup(mfaToken: string, code: string): Promise<PendingSession> {
    const res = await apiClient.post('/auth/mfa/setup/confirm', { mfa_token: mfaToken, code: code.trim() })
    return { recoveryCodes: res.data.recovery_codes || [], finish: () => commitSession(res.data) }
  }

  function logout() {
    // Best-effort server-side revocation of the refresh token (Module: session
    // security) - fire-and-forget so logout still feels instant even if the
    // network is slow; local session state is cleared immediately either way.
    const refreshToken = localStorage.getItem('cdr_refresh_token')
    if (refreshToken) {
      apiClient.post('/auth/logout', { refresh_token: refreshToken }).catch(() => { /* already logging out locally regardless */ })
    }
    localStorage.removeItem('cdr_token')
    localStorage.removeItem('cdr_refresh_token')
    localStorage.removeItem('cdr_user')
    setUser(null)
  }

  async function refreshUser() {
    const res = await apiClient.get('/auth/me')
    localStorage.setItem('cdr_user', JSON.stringify(res.data))
    setUser(res.data)
  }

  return (
    <AuthContext.Provider value={{ user, login, verifyCode, beginMfaSetup, confirmMfaSetup, logout, refreshUser, isLoading, error }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
