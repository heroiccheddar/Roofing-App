import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login as apiLogin, setAuthToken } from '../api/client'
import useAppStore from '../stores/appStore'

function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { setToken, setUser } = useAppStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const response = await apiLogin(email, password)
      setAuthToken(response.access_token)
      setToken(response.access_token)
      // Decode JWT to get user info (or fetch from /account endpoint)
      // For now, set basic user info from email
      setUser({ id: '', email, companyName: '' })
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={styles.title}>StormLeads</h1>
        <p style={styles.subtitle}>Storm damage lead intelligence for roofers</p>
        <form onSubmit={handleSubmit}>
          {error && <div style={styles.error}>{error}</div>}
          <div style={styles.field}>
            <label style={styles.label}>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              style={styles.input}
              placeholder="you@company.com"
            />
          </div>
          <div style={styles.field}>
            <label style={styles.label}>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={styles.input}
              placeholder="••••••••"
            />
          </div>
          <button type="submit" disabled={loading} style={styles.button}>
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}

// Use inline styles (keep it simple, no CSS framework needed for MVP)
const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex', justifyContent: 'center', alignItems: 'center',
    height: '100vh', background: '#f8fafc',
  },
  card: {
    width: '100%', maxWidth: 400, padding: 32,
    background: '#fff', borderRadius: 12, boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
  },
  title: { margin: 0, fontSize: 28, fontWeight: 700, color: '#0f172a' },
  subtitle: { margin: '8px 0 24px', fontSize: 14, color: '#64748b' },
  error: {
    padding: '8px 12px', marginBottom: 16, borderRadius: 6,
    background: '#fef2f2', color: '#dc2626', fontSize: 14,
  },
  field: { marginBottom: 16 },
  label: { display: 'block', marginBottom: 4, fontSize: 14, fontWeight: 500, color: '#374151' },
  input: {
    width: '100%', padding: '10px 12px', border: '1px solid #d1d5db',
    borderRadius: 6, fontSize: 14, outline: 'none', boxSizing: 'border-box',
  },
  button: {
    width: '100%', padding: 12, border: 'none', borderRadius: 6,
    background: '#2563eb', color: '#fff', fontSize: 16, fontWeight: 600,
    cursor: 'pointer',
  },
}

export default Login
