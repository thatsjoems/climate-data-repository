import axios from 'axios'
import { signInPath } from '../portal'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

/**
 * Where the sign-in tokens live (observation O2 of docs/PENTEST_CHECKLIST.md).
 *
 *  - The ACCESS token (short-lived) is kept in this variable, in memory only. It is never written to localStorage, so a script that gets into the page
 *    cannot find it in storage, and it disappears when the page is closed or reloaded.
 *  - The REFRESH token (long-lived) is not here at all: the server keeps it in an HttpOnly cookie that no script can read. The browser sends that cookie
 *    only to /api/auth/*, and a reloaded page uses it (POST /auth/refresh) to get a new access token.
 *  - The only thing left in localStorage is a harmless "a session may exist" hint, so a visitor who never signed in does not make a pointless refresh call.
 */
let accessToken: string | null = null
export function setAccessToken(token: string | null) { accessToken = token }
export function getAccessToken(): string | null { return accessToken }

const HINT_KEY = 'cdr_session'
export function hasSessionHint(): boolean {
  try { return localStorage.getItem(HINT_KEY) === '1' } catch { return false }
}
export function setSessionHint(on: boolean) {
  try { if (on) localStorage.setItem(HINT_KEY, '1'); else localStorage.removeItem(HINT_KEY) } catch { /* private window: no hint, the page asks the server instead */ }
}

// Earlier versions kept both tokens and the user in localStorage. Remove whatever is left of them, so nothing old stays readable in the browser.
function purgeLegacyStorage() {
  try {
    localStorage.removeItem('cdr_token')
    localStorage.removeItem('cdr_refresh_token')
    localStorage.removeItem('cdr_user')
  } catch { /* nothing to remove */ }
}
purgeLegacyStorage()

// The header only this application adds to the two requests that use the cookie (refresh, logout); a page on another site cannot add it.
export const WEB_CLIENT_HEADERS = { 'X-CDR-Client': 'web' }

export const apiClient = axios.create({
  baseURL: API_URL,
  withCredentials: true,      // sends the refresh cookie to /api/auth/* (it is not sent anywhere else)
})

// Automatically attach the current access token to every request
apiClient.interceptors.request.use((config) => {
  if (accessToken && config.headers) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  return config
})

function clearSessionAndRedirect() {
  accessToken = null
  setSessionHint(false)
  window.location.href = signInPath()      // the same door the person signed in through
}

export interface RefreshedSession {
  access_token: string
  user: any
}

// Session security (Module: token refresh): the access token is short-lived on purpose. When it expires, or when the page has just been opened, this
// exchanges the refresh cookie for a new access token (the server also rotates the cookie).
//
// `refreshPromise` is shared across every simultaneous caller so a page that fires several requests at once triggers exactly ONE refresh call.
// Across tabs the calls take turns (Web Locks): each tab's refresh then uses the cookie the previous one just replaced, instead of presenting a cookie
// that has already been rotated, which the server would treat as a stolen copy.
let refreshPromise: Promise<RefreshedSession> | null = null

async function callRefresh(): Promise<RefreshedSession> {
  // A plain axios call (not apiClient) - deliberately bypasses both interceptors so a failed refresh can never recursively trigger another refresh.
  const res = await axios.post(`${API_URL}/auth/refresh`, null, { withCredentials: true, headers: WEB_CLIENT_HEADERS })
  accessToken = res.data.access_token
  return res.data
}

export function refreshSession(): Promise<RefreshedSession> {
  if (!refreshPromise) {
    const locks = (typeof navigator !== 'undefined' ? (navigator as any).locks : undefined)
    const run = locks?.request ? locks.request('cdr-refresh', callRefresh) : callRefresh()
    refreshPromise = Promise.resolve(run).finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

// How many requests are waiting for the server (the thin progress bar at the top of the page shows it).
let pending = 0
const pendingListeners = new Set<(n: number) => void>()
function changePending(by: number) {
  pending = Math.max(0, pending + by)
  pendingListeners.forEach((f) => f(pending))
}
export const getPending = () => pending
export function subscribePending(f: (n: number) => void): () => void {
  pendingListeners.add(f)
  return () => { pendingListeners.delete(f) }
}
apiClient.interceptors.request.use((config) => { changePending(1); return config })
// Registered BEFORE the refresh handler below, so it sees every answer once; a retry after a refresh is a new request and counts again.
apiClient.interceptors.response.use(
  (response) => { changePending(-1); return response },
  (error) => { changePending(-1); return Promise.reject(error) },
)

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // Never attempt to "refresh" a failed login or a failed refresh itself -
    // those 401s mean "wrong credentials" / "refresh token itself is dead",
    // not "access token expired", and treating them as such would loop.
    const url: string = originalRequest?.url || ''
    // The steps of signing in (password, code, set-up) answer 401 for a WRONG code: that is a message for the person, never a reason
    // to refresh a token or to send them back to the start.
    const isSignInStep = url.includes('/auth/login') || url.includes('/auth/mfa/')   // verify, setup and the new recovery codes: a wrong code is a 401 that is only a message
    const isAuthEndpoint = isSignInStep || url.includes('/auth/refresh')

    if (error.response?.status === 401 && !isAuthEndpoint && !originalRequest._retry) {
      originalRequest._retry = true
      try {
        const session = await refreshSession()
        originalRequest.headers.Authorization = `Bearer ${session.access_token}`
        return apiClient(originalRequest)
      } catch {
        clearSessionAndRedirect()
        return Promise.reject(error)
      }
    }

    if (error.response?.status === 401 && (isAuthEndpoint || originalRequest?._retry)) {
      // Login's own 401 (wrong password) must NOT redirect - the Login page
      // handles that error message itself. A retried request that still
      // fails, or a dead refresh token, means the session is truly over.
      if (isSignInStep) {
        return Promise.reject(error)
      }
      clearSessionAndRedirect()
    }

    return Promise.reject(error)
  }
)

export default apiClient
