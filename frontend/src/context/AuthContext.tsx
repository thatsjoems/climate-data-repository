import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import apiClient, { WEB_CLIENT_HEADERS, hasSessionHint, refreshSession, setAccessToken, setSessionHint } from '../api/client'
import { Portal, portalOfRole, rememberPortal } from '../portal'

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
  login: (username: string, password: string, portal?: Portal) => Promise<SignInResult>
  verifyCode: (mfaToken: string, entry: { code?: string; recoveryCode?: string }) => Promise<void>
  beginMfaSetup: (mfaToken: string) => Promise<SetupInfo>
  confirmMfaSetup: (mfaToken: string, code: string) => Promise<PendingSession>
  logout: () => void
  refreshUser: () => Promise<void>
  ready: boolean          // false only while a reloaded page is asking the server whether the person is still signed in
  isLoading: boolean
  error: string | null
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  // Nothing about the session is kept in the browser's storage (observation O2). A page that is opened or reloaded asks the server, which answers from
  // the HttpOnly refresh cookie: a new access token (kept in memory) and who the person is.
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [ready, setReady] = useState<boolean>(() => !hasSessionHint())
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (ready) return
    let cancelled = false
    refreshSession()
      .then((session) => {
        if (cancelled) return
        rememberPortal(portalOfRole(session.user.role))
        setUser(session.user)
      })
      .catch(() => { setSessionHint(false) })        // no valid session any more: the person signs in again
      .finally(() => { if (!cancelled) setReady(true) })
    return () => { cancelled = true }
  }, [])        // eslint-disable-line react-hooks/exhaustive-deps

  function commitSession(data: any) {
    setAccessToken(data.access_token)
    setSessionHint(true)
    rememberPortal(portalOfRole(data.user.role))
    setUser(data.user)
  }

  async function login(username: string, password: string, portal?: Portal): Promise<SignInResult> {
    setIsLoading(true)
    setError(null)
    try {
      const res = await apiClient.post('/auth/login', portal ? { username, password, portal } : { username, password })
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
    // Server-side revocation of the refresh token, and the order to delete the cookie (Module: session security) - fire-and-forget so logout
    // still feels instant even if the network is slow; local session state is cleared immediately either way.
    apiClient.post('/auth/logout', null, { headers: WEB_CLIENT_HEADERS }).catch(() => { /* already logging out locally regardless */ })
    setAccessToken(null)
    setSessionHint(false)
    setUser(null)
  }

  async function refreshUser() {
    const res = await apiClient.get('/auth/me')
    setUser(res.data)
  }

  return (
    <AuthContext.Provider value={{ user, login, verifyCode, beginMfaSetup, confirmMfaSetup, logout, refreshUser, ready, isLoading, error }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
