import { Routes, Route } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import Navbar from './components/Navbar'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import RequestAccess from './pages/RequestAccess'
import InstitutionPortal from './pages/InstitutionPortal'
import InternalPortal from './pages/InternalPortal'
import AdminPanel from './pages/AdminPanel'

function HomeRouter() {
  const { user } = useAuth()
  if (!user) return null
  if (user.role === 'INSTITUTION_USER') return <InstitutionPortal />
  return <InternalPortal />
}

export default function App() {
  return (
    <div className="app-shell">
      <Navbar />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/request-access" element={<RequestAccess />} />
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
      </Routes>
    </div>
  )
}
