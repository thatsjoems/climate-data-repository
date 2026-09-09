import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import RequestAccess from './pages/RequestAccess'
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
  return (
    <div className="app-shell">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/request-access" element={<RequestAccess />} />
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
