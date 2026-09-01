import { createContext, useContext, useState, ReactNode } from 'react'
import apiClient from '../api/client'

export interface CurrentUser {
  id: string
  full_name: string
  username: string
  email: string
  role: 'SYSTEM_ADMIN' | 'BOT_USER' | 'INSTITUTION_USER'
  institution_id: string | null
}

interface AuthContextType {
  user: CurrentUser | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
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
      localStorage.setItem('cdr_user', JSON.stringify(res.data.user))
      setUser(res.data.user)
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Imeshindikana kuingia. Jaribu tena.'
      setError(msg)
      throw err
    } finally {
      setIsLoading(false)
    }
  }

  function logout() {
    localStorage.removeItem('cdr_token')
    localStorage.removeItem('cdr_user')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, login, logout, isLoading, error }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
