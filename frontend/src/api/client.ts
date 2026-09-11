import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

export const apiClient = axios.create({
  baseURL: API_URL,
})

// Automatically attach the current access token to every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('cdr_token')
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

function clearSessionAndRedirect() {
  localStorage.removeItem('cdr_token')
  localStorage.removeItem('cdr_refresh_token')
  localStorage.removeItem('cdr_user')
  window.location.href = '/login'
}

// Session security (Module: token refresh): the access token is short-lived
// on purpose. When it expires, this transparently exchanges the refresh
// token for a new access token and retries the original request once -
// the user never notices, no forced re-login every few minutes.
//
// `refreshPromise` is shared across every simultaneous 401 so a page that
// fires several requests at once triggers exactly ONE refresh call, not one
// per failed request - everyone else just awaits the same in-flight promise.
let refreshPromise: Promise<string> | null = null

async function performRefresh(): Promise<string> {
  const refreshToken = localStorage.getItem('cdr_refresh_token')
  if (!refreshToken) {
    throw new Error('No refresh token available')
  }
  // A plain axios call (not apiClient) - deliberately bypasses both
  // interceptors above so a failed refresh can never recursively trigger
  // another refresh attempt.
  const res = await axios.post(`${API_URL}/auth/refresh`, { refresh_token: refreshToken })
  localStorage.setItem('cdr_token', res.data.access_token)
  localStorage.setItem('cdr_refresh_token', res.data.refresh_token)
  return res.data.access_token
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // Never attempt to "refresh" a failed login or a failed refresh itself -
    // those 401s mean "wrong credentials" / "refresh token itself is dead",
    // not "access token expired", and treating them as such would loop.
    const isAuthEndpoint = originalRequest?.url?.includes('/auth/login') || originalRequest?.url?.includes('/auth/refresh')

    if (error.response?.status === 401 && !isAuthEndpoint && !originalRequest._retry) {
      originalRequest._retry = true
      try {
        if (!refreshPromise) {
          refreshPromise = performRefresh().finally(() => { refreshPromise = null })
        }
        const newAccessToken = await refreshPromise
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`
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
      if (originalRequest?.url?.includes('/auth/login')) {
        return Promise.reject(error)
      }
      clearSessionAndRedirect()
    }

    return Promise.reject(error)
  }
)

export default apiClient
