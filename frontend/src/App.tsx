import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import RequestProgress from './components/RequestProgress'
import Login from './pages/Login'
import StaffLogin from './pages/StaffLogin'
import ForgotPassword from './pages/ForgotPassword'
import InstitutionPortal from './pages/InstitutionPortal'
import InternalPortal from './pages/InternalPortal'
import AdminPanel from './pages/AdminPanel'
import ChangePassword from './pages/ChangePassword'

function HomeRouter() {
  const { user } = useAuth()
  if (!user) return null
  if (user.role === 'INSTITUTION_USER') return <InstitutionPortal />
  // SYSTEM_ADMIN has its own dedicated home (administration only - no climate/
  // submissions data). BOT_USER is the only role that lands on the data dashboard.
  if (user.role === 'SYSTEM_ADMIN') return <Navigate to="/admin" replace />
  return <InternalPortal />
}

export default function App() {
  const { ready } = useAuth()
  if (ready === false) return <div className="loading-screen" role="status">Loading…</div>      // see AuthContext: the server is being asked whether the person is still signed in
  return (
    <div className="app-shell">
      <RequestProgress />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/staff/login" element={<StaffLogin />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <HomeRouter />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute allowedRoles={['SYSTEM_ADMIN']}>
              <AdminPanel />
            </ProtectedRoute>
          }
        />
        <Route
          path="/change-password"
          element={
            <ProtectedRoute>
              <ChangePassword />
            </ProtectedRoute>
          }
        />
      </Routes>
    </div>
  )
}
