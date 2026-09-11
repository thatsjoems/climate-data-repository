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
}

interface AuthContextType {
  user: CurrentUser | null
  login: (username: string, password: string) => Promise<void>
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

  async function login(username: string, password: string) {
    setIsLoading(true)
    setError(null)
    try {
      const res = await apiClient.post('/auth/login', { username, password })
      localStorage.setItem('cdr_token', res.data.access_token)
      localStorage.setItem('cdr_refresh_token', res.data.refresh_token)
      localStorage.setItem('cdr_user', JSON.stringify(res.data.user))
      setUser(res.data.user)
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Login failed. Please try again.'
      setError(msg)
      throw err
    } finally {
      setIsLoading(false)
    }
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
    <AuthContext.Provider value={{ user, login, logout, refreshUser, isLoading, error }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
