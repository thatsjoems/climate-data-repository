import { useState, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const { login, isLoading, error } = useAuth()
  const navigate = useNavigate()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    try {
      await login(username, password)
      navigate('/')
    } catch {
      // error is already surfaced via AuthContext
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <h1>Climate Data Repository</h1>
        <p className="login-subtitle">Bank of Tanzania - Financial Stability Department</p>

        {error && <div className="alert-error">{error}</div>}

        <label>Username</label>
        <input
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          autoFocus
        />

        <label>Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        <button type="submit" disabled={isLoading}>
          {isLoading ? 'Signing in...' : 'Log In'}
        </button>

        <div className="demo-hint">
          <strong>DEMO accounts (after running init_db.py):</strong>
          <ul>
            <li>Admin: <code>admin</code> / <code>Admin@123</code></li>
            <li>BOT Analyst: <code>bot_analyst</code> / <code>Analyst@123</code></li>
            <li>Institution (Bank A): <code>bankA_user</code> / <code>BankA@123</code></li>
          </ul>
        </div>
      </form>
    </div>
  )
}
