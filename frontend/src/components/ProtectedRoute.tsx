import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { onlyStaff, signInPath } from '../portal'

export default function ProtectedRoute({
  children,
  allowedRoles,
}: {
  children: JSX.Element
  allowedRoles?: string[]
}) {
  const { user, ready } = useAuth()
  const location = useLocation()

  // A reloaded page is still asking the server whether the person is signed in: do not send them to the sign-in page meanwhile.
  if (ready === false) return <div className="loading-screen" role="status">Loading…</div>
  if (!user) {
    return <Navigate to={onlyStaff(allowedRoles) ? signInPath('internal') : signInPath()} replace />
  }
  // Force a password change before anything else if the account still has a
  // temporary/admin-issued password - the user can't navigate around this.
  if (user.must_change_password && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />
  }
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />
  }
  return children
}
