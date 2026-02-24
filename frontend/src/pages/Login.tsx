import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login as apiLogin, register as apiRegister, setAuthToken } from '../api/client'
import useAppStore from '../stores/appStore'
import { useMediaQuery } from '../hooks/useMediaQuery'

function Login() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [lat, setLat] = useState('33.749')
  const [lon, setLon] = useState('-84.388')
  const [radiusKm, setRadiusKm] = useState('80')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { setToken, setUser, setHome } = useAppStore()
  const isMobile = useMediaQuery('(max-width: 767px)')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      let response
      if (mode === 'login') {
        response = await apiLogin(email, password)
      } else {
        response = await apiRegister({
          email,
          password,
          company_name: companyName,
          phone_number: phoneNumber || undefined,
          service_area_lat: parseFloat(lat),
          service_area_lon: parseFloat(lon),
          service_area_radius_km: parseFloat(radiusKm),
        })
      }
      setAuthToken(response.access_token)
      setToken(response.access_token)
      setUser({ id: '', email, companyName })
      // Set home location (use registration coords, or default Atlanta for login)
      const homeLat = mode === 'register' ? parseFloat(lat) : 33.749
      const homeLon = mode === 'register' ? parseFloat(lon) : -84.388
      setHome(homeLat, homeLon)
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : `${mode === 'login' ? 'Login' : 'Registration'} failed`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.container}>
      <div style={{ ...styles.card, padding: isMobile ? 20 : 32 }}>
        <h1 style={styles.title}>RoofIQ</h1>
        <p style={styles.subtitle}>Roofing lead intelligence for professionals</p>
        <div style={styles.tabs}>
          <button
            style={mode === 'login' ? styles.tabActive : styles.tab}
            onClick={() => { setMode('login'); setError('') }}
            type="button"
          >Sign In</button>
          <button
            style={mode === 'register' ? styles.tabActive : styles.tab}
            onClick={() => { setMode('register'); setError('') }}
            type="button"
          >Register</button>
        </div>
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
              minLength={8}
              style={styles.input}
              placeholder="••••••••"
            />
          </div>
          {mode === 'register' && (
            <>
              <div style={styles.field}>
                <label style={styles.label}>Company Name</label>
                <input
                  type="text"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  required
                  style={styles.input}
                  placeholder="Acme Roofing"
                />
              </div>
              <div style={styles.field}>
                <label style={styles.label}>Phone (optional)</label>
                <input
                  type="tel"
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  style={styles.input}
                  placeholder="(555) 123-4567"
                />
              </div>
              <div style={{ ...styles.fieldRow, flexDirection: isMobile ? 'column' : 'row', gap: isMobile ? 0 : 12 }}>
                <div style={styles.fieldHalf}>
                  <label style={styles.label}>Center Lat</label>
                  <input
                    type="number"
                    step="any"
                    value={lat}
                    onChange={(e) => setLat(e.target.value)}
                    required
                    style={styles.input}
                  />
                </div>
                <div style={styles.fieldHalf}>
                  <label style={styles.label}>Center Lon</label>
                  <input
                    type="number"
                    step="any"
                    value={lon}
                    onChange={(e) => setLon(e.target.value)}
                    required
                    style={styles.input}
                  />
                </div>
              </div>
              <div style={styles.field}>
                <label style={styles.label}>Service Area Radius (km)</label>
                <input
                  type="number"
                  step="any"
                  min="1"
                  max="500"
                  value={radiusKm}
                  onChange={(e) => setRadiusKm(e.target.value)}
                  required
                  style={styles.input}
                />
              </div>
              <p style={styles.hint}>Defaults to ~80km around Atlanta, GA. Adjust to your coverage area.</p>
            </>
          )}
          <button type="submit" disabled={loading} style={styles.button}>
            {loading
              ? (mode === 'login' ? 'Signing in...' : 'Creating account...')
              : (mode === 'login' ? 'Sign In' : 'Create Account')}
          </button>
        </form>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex', justifyContent: 'center', alignItems: 'center',
    minHeight: '100dvh', background: '#f8fafc', padding: 16,
  },
  card: {
    width: '100%', maxWidth: 400, padding: 32,
    background: '#fff', borderRadius: 12, boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
  },
  title: { margin: 0, fontSize: 28, fontWeight: 700, color: '#0f172a' },
  subtitle: { margin: '8px 0 16px', fontSize: 14, color: '#64748b' },
  tabs: {
    display: 'flex', gap: 0, marginBottom: 20,
    borderBottom: '2px solid #e5e7eb',
  },
  tab: {
    flex: 1, padding: '8px 0', border: 'none', background: 'none',
    fontSize: 14, fontWeight: 500, color: '#9ca3af', cursor: 'pointer',
    borderBottom: '2px solid transparent', marginBottom: -2,
  },
  tabActive: {
    flex: 1, padding: '8px 0', border: 'none', background: 'none',
    fontSize: 14, fontWeight: 600, color: '#2563eb', cursor: 'pointer',
    borderBottom: '2px solid #2563eb', marginBottom: -2,
  },
  error: {
    padding: '8px 12px', marginBottom: 16, borderRadius: 6,
    background: '#fef2f2', color: '#dc2626', fontSize: 14,
  },
  field: { marginBottom: 16 },
  fieldRow: { display: 'flex', gap: 12, marginBottom: 16 },
  fieldHalf: { flex: 1, marginBottom: 16 },
  label: { display: 'block', marginBottom: 4, fontSize: 14, fontWeight: 500, color: '#374151' },
  input: {
    width: '100%', padding: '10px 12px', border: '1px solid #d1d5db',
    borderRadius: 6, fontSize: 14, outline: 'none', boxSizing: 'border-box',
  },
  hint: { margin: '-8px 0 16px', fontSize: 12, color: '#9ca3af' },
  button: {
    width: '100%', padding: 12, border: 'none', borderRadius: 6,
    background: '#2563eb', color: '#fff', fontSize: 16, fontWeight: 600,
    cursor: 'pointer',
  },
}

export default Login
