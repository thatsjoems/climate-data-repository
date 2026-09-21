import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import ProtectedRoute from '../components/ProtectedRoute'
import * as AuthContext from '../context/AuthContext'
import type { CurrentUser } from '../context/AuthContext'

// ProtectedRoute is the ONE place that decides "can this logged-in browser
// actually see this screen" on the frontend - the same role/permission
// story the backend enforces (see backend/tests/test_rbac_and_isolation.py),
// just at the routing layer. Every branch here is a real access-control
// decision, not incidental UI behaviour, so each one gets its own test
// rather than one combined "it renders" smoke test.

function mockUser(overrides: Partial<CurrentUser> = {}): CurrentUser {
  return {
    id: 'u1',
    full_name: 'Test User',
    username: 'testuser',
    email: 't@example.com',
    role: 'BOT_USER',
    institution_id: null,
    must_change_password: false,
    ...overrides,
  }
}

function renderProtected(
  user: CurrentUser | null,
  allowedRoles?: string[],
  initialPath = '/dashboard'
) {
  vi.spyOn(AuthContext, 'useAuth').mockReturnValue({
    user,
    login: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
    isLoading: false,
    error: null,
  })

  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<div>Login Screen</div>} />
        <Route path="/change-password" element={<div>Change Password Screen</div>} />
        <Route path="/" element={<div>Home Screen</div>} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute allowedRoles={allowedRoles}>
              <div>Protected Content</div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>
  )
}

describe('ProtectedRoute', () => {
  it('redirects an unauthenticated visitor to /login', () => {
    renderProtected(null)
    expect(screen.getByText('Login Screen')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('forces a password change before anything else when must_change_password is true', () => {
    renderProtected(mockUser({ must_change_password: true }))
    expect(screen.getByText('Change Password Screen')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('does not redirect-loop when already on /change-password', () => {
    renderProtected(mockUser({ must_change_password: true }), undefined, '/change-password')
    expect(screen.getByText('Change Password Screen')).toBeInTheDocument()
  })

  it('redirects away when the user\'s role is not in allowedRoles - the actual tenant/role isolation check', () => {
    renderProtected(mockUser({ role: 'INSTITUTION_USER' }), ['SYSTEM_ADMIN'])
    expect(screen.getByText('Home Screen')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('renders the protected content when the role IS allowed', () => {
    renderProtected(mockUser({ role: 'BOT_USER' }), ['BOT_USER', 'SYSTEM_ADMIN'])
    expect(screen.getByText('Protected Content')).toBeInTheDocument()
  })

  it('renders for any authenticated user when no allowedRoles is specified', () => {
    renderProtected(mockUser({ role: 'INSTITUTION_USER' }))
    expect(screen.getByText('Protected Content')).toBeInTheDocument()
  })
})
