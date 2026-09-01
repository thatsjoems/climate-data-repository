import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  if (!user) return null

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <span className="navbar-title">Climate Data Repository</span>
        <span className="navbar-subtitle">Bank of Tanzania</span>
      </div>
      <div className="navbar-links">
        {user.role === 'INSTITUTION_USER' && <Link to="/">Dashboard Yangu</Link>}
        {(user.role === 'BOT_USER' || user.role === 'SYSTEM_ADMIN') && <Link to="/">Dashboard ya Ndani</Link>}
        {user.role === 'SYSTEM_ADMIN' && <Link to="/admin">Usimamizi (Admin)</Link>}
      </div>
      <div className="navbar-user">
        <span>{user.full_name} <em>({user.role})</em></span>
        <button onClick={handleLogout}>Toka (Logout)</button>
      </div>
    </nav>
  )
}
