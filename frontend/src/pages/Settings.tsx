import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getAccount, updateProfile, updateServiceArea, updateAlertPreferences } from '../api/client'
import type { AccountResponse } from '../types/api'
import { useDarkMode } from '../hooks/useDarkMode'
import useAppStore from '../stores/appStore'

export default function Settings() {
  const navigate = useNavigate()
  const { darkMode, toggleDarkMode } = useDarkMode()
  const setUser = useAppStore((s) => s.setUser)
  const setHome = useAppStore((s) => s.setHome)
  const logout = useAppStore((s) => s.logout)

  // Account state
  const [account, setAccount] = useState<AccountResponse | null>(null)
  const [companyName, setCompanyName] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileMsg, setProfileMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // Service area state
  const [saCity, setSaCity] = useState('')
  const [saRadiusMiles, setSaRadiusMiles] = useState('50')
  const [saLoading, setSaLoading] = useState(false)
  const [saMsg, setSaMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [geolocating, setGeolocating] = useState(false)

  // Alert preferences state
  const [minScore, setMinScore] = useState(70)
  const [minHail, setMinHail] = useState(1.0)
  const [channels, setChannels] = useState<string[]>(['email'])
  const [quietEnabled, setQuietEnabled] = useState(false)
  const [quietStart, setQuietStart] = useState('22:00')
  const [quietEnd, setQuietEnd] = useState('07:00')
  const [alertLoading, setAlertLoading] = useState(false)
  const [alertMsg, setAlertMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const [loading, setLoading] = useState(true)

  const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''

  // Reverse-geocode lat/lon → city name
  const reverseGeocode = async (lat: number, lon: number): Promise<string> => {
    try {
      const res = await fetch(`https://api.mapbox.com/geocoding/v5/mapbox.places/${lon},${lat}.json?types=place&limit=1&access_token=${MAPBOX_TOKEN}`)
      const data = await res.json()
      if (data.features?.length > 0) return data.features[0].place_name
    } catch { /* fall through */ }
    return `${lat.toFixed(4)}, ${lon.toFixed(4)}`
  }

  // Forward-geocode city name → lat/lon
  const forwardGeocode = async (query: string): Promise<{ lat: number; lon: number } | null> => {
    try {
      const res = await fetch(`https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(query)}.json?types=place,locality,address&limit=1&country=us&access_token=${MAPBOX_TOKEN}`)
      const data = await res.json()
      if (data.features?.length > 0) {
        const [lon, lat] = data.features[0].center
        return { lat, lon }
      }
    } catch { /* fall through */ }
    return null
  }

  useEffect(() => {
    getAccount().then(async (acct) => {
      setAccount(acct)
      setCompanyName(acct.company_name)
      setPhoneNumber(acct.phone_number || '')
      // Reverse-geocode service area centroid to a city name
      if (acct.service_area_lat != null && acct.service_area_lon != null) {
        const name = await reverseGeocode(acct.service_area_lat, acct.service_area_lon)
        setSaCity(name)
      }
      const prefs = acct.alert_preferences || {}
      setMinScore(prefs.min_score ?? 70)
      setMinHail(prefs.min_hail_inches ?? 1.0)
      setChannels(prefs.channels ?? ['email'])
      if (prefs.quiet_hours) {
        setQuietEnabled(true)
        setQuietStart(prefs.quiet_hours.start)
        setQuietEnd(prefs.quiet_hours.end)
      }
    }).finally(() => setLoading(false))
  }, [])

  const handleSaveProfile = async () => {
    setProfileLoading(true)
    setProfileMsg(null)
    try {
      const updated = await updateProfile({
        company_name: companyName,
        phone_number: phoneNumber || undefined,
      })
      setAccount(updated)
      setUser({ id: updated.id, email: updated.email, companyName: updated.company_name })
      setProfileMsg({ type: 'success', text: 'Profile updated' })
    } catch (err) {
      setProfileMsg({ type: 'error', text: err instanceof Error ? err.message : 'Failed to update profile' })
    } finally {
      setProfileLoading(false)
    }
  }

  const handleSaveServiceArea = async () => {
    setSaLoading(true)
    setSaMsg(null)
    try {
      if (!saCity.trim()) throw new Error('Please enter a city')
      const radiusMiles = parseFloat(saRadiusMiles)
      if (isNaN(radiusMiles) || radiusMiles <= 0) throw new Error('Please enter a valid radius')
      const radiusKm = radiusMiles * 1.60934
      const coords = await forwardGeocode(saCity.trim())
      if (!coords) throw new Error('Could not find that location. Try a more specific city name.')
      const updated = await updateServiceArea(coords.lat, coords.lon, radiusKm)
      setAccount(updated)
      if (updated.service_area_lat != null && updated.service_area_lon != null) {
        setHome(updated.service_area_lat, updated.service_area_lon)
        const name = await reverseGeocode(updated.service_area_lat, updated.service_area_lon)
        setSaCity(name)
      }
      setSaMsg({ type: 'success', text: 'Service area updated' })
    } catch (err) {
      setSaMsg({ type: 'error', text: err instanceof Error ? err.message : 'Failed to update' })
    } finally {
      setSaLoading(false)
    }
  }

  const handleUseMyLocation = () => {
    if (!navigator.geolocation) {
      setSaMsg({ type: 'error', text: 'Geolocation is not supported by your browser' })
      return
    }
    setGeolocating(true)
    setSaMsg(null)
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const name = await reverseGeocode(pos.coords.latitude, pos.coords.longitude)
        setSaCity(name)
        setGeolocating(false)
      },
      (err) => {
        setSaMsg({ type: 'error', text: err.message || 'Failed to get location' })
        setGeolocating(false)
      },
      { enableHighAccuracy: false, timeout: 10000 },
    )
  }

  const toggleChannel = (ch: string) => {
    setChannels(prev => prev.includes(ch) ? prev.filter(c => c !== ch) : [...prev, ch])
  }

  const handleSaveAlerts = async () => {
    setAlertLoading(true)
    setAlertMsg(null)
    try {
      await updateAlertPreferences({
        min_score: minScore,
        min_hail_inches: minHail,
        channels,
        quiet_hours: quietEnabled ? { start: quietStart, end: quietEnd } : undefined,
      })
      setAlertMsg({ type: 'success', text: 'Alert preferences updated' })
    } catch (err) {
      setAlertMsg({ type: 'error', text: err instanceof Error ? err.message : 'Failed to update' })
    } finally {
      setAlertLoading(false)
    }
  }

  const cardStyle: React.CSSProperties = {
    background: 'var(--card-bg)',
    border: '1px solid var(--card-border)',
    borderRadius: 12,
    padding: '20px',
    marginBottom: 20,
  }

  const sectionTitleStyle: React.CSSProperties = {
    fontSize: 16,
    fontWeight: 700,
    color: 'var(--text-primary)',
    marginBottom: 16,
    marginTop: 0,
  }

  const fieldWrapStyle: React.CSSProperties = {
    marginBottom: 14,
  }

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: 12,
    fontWeight: 600,
    color: 'var(--text-secondary)',
    marginBottom: 4,
    textTransform: 'uppercase',
  }

  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 12px',
    borderRadius: 8,
    border: '1px solid var(--input-border)',
    background: 'var(--input-bg)',
    color: 'var(--text-primary)',
    fontSize: 14,
    boxSizing: 'border-box',
  }

  const readOnlyInputStyle: React.CSSProperties = {
    ...inputStyle,
    opacity: 0.6,
    cursor: 'not-allowed',
  }

  const saveButtonStyle = (saving: boolean): React.CSSProperties => ({
    padding: '10px 24px',
    borderRadius: 8,
    border: 'none',
    background: saving ? 'var(--bg-tertiary)' : 'var(--accent-blue)',
    color: '#fff',
    fontSize: 14,
    fontWeight: 600,
    cursor: saving ? 'not-allowed' : 'pointer',
  })

  const msgStyle = (type: 'success' | 'error'): React.CSSProperties => ({
    marginTop: 10,
    padding: '8px 12px',
    borderRadius: 8,
    fontSize: 13,
    background: type === 'success' ? 'var(--success-bg)' : 'var(--error-bg)',
    color: type === 'success' ? 'var(--success-text, #16a34a)' : 'var(--error-text)',
    border: `1px solid ${type === 'success' ? 'var(--success-border, #bbf7d0)' : 'var(--error-border)'}`,
  })

  if (loading) {
    return (
      <div style={{
        position: 'fixed', inset: 0, zIndex: 200,
        background: 'var(--bg-primary)', color: 'var(--text-primary)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'system-ui, -apple-system, sans-serif',
      }}>
        Loading...
      </div>
    )
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 200,
      background: 'var(--bg-primary)', color: 'var(--text-primary)',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* Sticky header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '12px 16px',
        borderBottom: '1px solid var(--border-primary)',
        background: 'var(--bg-primary)',
        flexShrink: 0,
        position: 'sticky', top: 0, zIndex: 10,
      }}>
        <button
          onClick={() => navigate('/')}
          style={{
            background: 'none', border: 'none',
            color: 'var(--accent-blue)',
            fontSize: 15, fontWeight: 600, cursor: 'pointer', padding: 0,
          }}
        >
          &larr; Back
        </button>
        <span style={{ fontWeight: 700, fontSize: 16, color: 'var(--text-primary)' }}>Settings</span>
        <button
          onClick={toggleDarkMode}
          style={{
            padding: '6px 14px', borderRadius: 8,
            border: '1px solid var(--border-primary)',
            background: darkMode ? 'var(--accent-blue)' : 'var(--bg-secondary)',
            color: darkMode ? '#fff' : 'var(--text-secondary)',
            fontSize: 13, fontWeight: 600, cursor: 'pointer',
          }}
        >
          {darkMode ? 'Dark' : 'Light'}
        </button>
      </div>

      {/* Scrollable body */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <div style={{ maxWidth: 720, margin: '0 auto', padding: '20px 16px' }}>

          {/* Section A — Account */}
          <div style={cardStyle}>
            <h2 style={sectionTitleStyle}>Account</h2>

            <div style={fieldWrapStyle}>
              <label style={labelStyle}>Email</label>
              <input
                type="email"
                value={account?.email ?? ''}
                readOnly
                style={readOnlyInputStyle}
              />
            </div>

            <div style={fieldWrapStyle}>
              <label style={labelStyle}>Company Name</label>
              <input
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                style={inputStyle}
              />
            </div>

            <div style={fieldWrapStyle}>
              <label style={labelStyle}>Phone Number</label>
              <input
                type="tel"
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
                style={inputStyle}
              />
            </div>

            <div style={{ display: 'flex', gap: 16, marginBottom: 14 }}>
              <div style={{ flex: 1 }}>
                <label style={labelStyle}>Member Since</label>
                <input
                  type="text"
                  value={account?.created_at
                    ? new Date(account.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
                    : ''}
                  readOnly
                  style={readOnlyInputStyle}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label style={labelStyle}>Subscription Tier</label>
                <div style={{ paddingTop: 6 }}>
                  <span style={{
                    display: 'inline-block',
                    padding: '4px 12px',
                    borderRadius: 20,
                    fontSize: 13,
                    fontWeight: 600,
                    background: account?.subscription_tier === 'pro' ? 'var(--accent-blue)' : 'var(--bg-secondary)',
                    color: account?.subscription_tier === 'pro' ? '#fff' : 'var(--text-secondary)',
                    border: '1px solid var(--border-primary)',
                    textTransform: 'capitalize',
                  }}>
                    {account?.subscription_tier ?? 'free'}
                  </span>
                </div>
              </div>
            </div>

            <button
              onClick={handleSaveProfile}
              disabled={profileLoading}
              style={saveButtonStyle(profileLoading)}
            >
              {profileLoading ? 'Saving...' : 'Save Profile'}
            </button>

            {profileMsg && (
              <div style={msgStyle(profileMsg.type)}>{profileMsg.text}</div>
            )}
          </div>

          {/* Section B — Service Area */}
          <div style={cardStyle}>
            <h2 style={sectionTitleStyle}>Service Area</h2>

            <div style={fieldWrapStyle}>
              <label style={labelStyle}>Home City</label>
              <input
                type="text"
                value={saCity}
                onChange={(e) => setSaCity(e.target.value)}
                style={inputStyle}
                placeholder="e.g. Denver, CO"
              />
            </div>

            <div style={{ display: 'flex', gap: 12, marginBottom: 14, alignItems: 'flex-end' }}>
              <div style={{ flex: 1 }}>
                <label style={labelStyle}>Radius (miles)</label>
                <input
                  type="number"
                  value={saRadiusMiles}
                  onChange={(e) => setSaRadiusMiles(e.target.value)}
                  style={{ ...inputStyle, maxWidth: 160 }}
                  min={1}
                  max={300}
                  placeholder="e.g. 50"
                />
              </div>
              <button
                onClick={handleUseMyLocation}
                disabled={geolocating}
                style={{
                  padding: '8px 14px', borderRadius: 8,
                  border: '1px solid var(--border-primary)',
                  background: 'var(--bg-secondary)',
                  color: 'var(--text-secondary)',
                  fontSize: 13, fontWeight: 600, cursor: geolocating ? 'not-allowed' : 'pointer',
                  whiteSpace: 'nowrap', flexShrink: 0,
                }}
              >
                {geolocating ? 'Locating...' : 'Use My Location'}
              </button>
            </div>

            <button
              onClick={handleSaveServiceArea}
              disabled={saLoading}
              style={saveButtonStyle(saLoading)}
            >
              {saLoading ? 'Saving...' : 'Update Service Area'}
            </button>

            {saMsg && (
              <div style={msgStyle(saMsg.type)}>{saMsg.text}</div>
            )}
          </div>

          {/* Section C — Alert Preferences */}
          <div style={cardStyle}>
            <h2 style={sectionTitleStyle}>Alert Preferences</h2>

            <div style={fieldWrapStyle}>
              <label style={labelStyle}>Min Score: {minScore}</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={minScore}
                  onChange={(e) => setMinScore(Number(e.target.value))}
                  style={{ flex: 1 }}
                />
                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', minWidth: 28, textAlign: 'right' }}>
                  {minScore}
                </span>
              </div>
            </div>

            <div style={fieldWrapStyle}>
              <label style={labelStyle}>Min Hail Size (inches)</label>
              <input
                type="number"
                value={minHail}
                onChange={(e) => setMinHail(Number(e.target.value))}
                step={0.25}
                min={0}
                style={{ ...inputStyle, maxWidth: 160 }}
              />
            </div>

            <div style={fieldWrapStyle}>
              <label style={labelStyle}>Channels</label>
              <div style={{ display: 'flex', gap: 20, marginTop: 6 }}>
                {(['email', 'sms', 'push'] as const).map((ch) => (
                  <label key={ch} style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 14, color: 'var(--text-primary)' }}>
                    <input
                      type="checkbox"
                      checked={channels.includes(ch)}
                      onChange={() => toggleChannel(ch)}
                      style={{ width: 15, height: 15, cursor: 'pointer' }}
                    />
                    {ch.charAt(0).toUpperCase() + ch.slice(1)}
                  </label>
                ))}
              </div>
            </div>

            <div style={fieldWrapStyle}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 14, color: 'var(--text-primary)', fontWeight: 600, marginBottom: 10 }}>
                <input
                  type="checkbox"
                  checked={quietEnabled}
                  onChange={(e) => setQuietEnabled(e.target.checked)}
                  style={{ width: 15, height: 15, cursor: 'pointer' }}
                />
                Enable Quiet Hours
              </label>

              {quietEnabled && (
                <div style={{ display: 'flex', gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <label style={labelStyle}>Start (HH:MM)</label>
                    <input
                      type="time"
                      value={quietStart}
                      onChange={(e) => setQuietStart(e.target.value)}
                      style={inputStyle}
                    />
                  </div>
                  <div style={{ flex: 1 }}>
                    <label style={labelStyle}>End (HH:MM)</label>
                    <input
                      type="time"
                      value={quietEnd}
                      onChange={(e) => setQuietEnd(e.target.value)}
                      style={inputStyle}
                    />
                  </div>
                </div>
              )}
            </div>

            <button
              onClick={handleSaveAlerts}
              disabled={alertLoading}
              style={saveButtonStyle(alertLoading)}
            >
              {alertLoading ? 'Saving...' : 'Save Preferences'}
            </button>

            {alertMsg && (
              <div style={msgStyle(alertMsg.type)}>{alertMsg.text}</div>
            )}
          </div>

          {/* Section D — Preferences / Danger Zone */}
          <div style={cardStyle}>
            <h2 style={sectionTitleStyle}>Preferences</h2>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <span style={{ fontSize: 14, color: 'var(--text-primary)' }}>Dark Mode</span>
              <button
                onClick={toggleDarkMode}
                style={{
                  padding: '6px 16px', borderRadius: 8,
                  border: '1px solid var(--border-primary)',
                  background: darkMode ? 'var(--accent-blue)' : 'var(--bg-secondary)',
                  color: darkMode ? '#fff' : 'var(--text-secondary)',
                  fontSize: 13, fontWeight: 600, cursor: 'pointer',
                }}
              >
                {darkMode ? 'On' : 'Off'}
              </button>
            </div>

            <button
              onClick={() => { logout(); navigate('/login') }}
              style={{
                width: '100%', padding: '10px', borderRadius: 8,
                border: '1px solid #ef4444', background: 'transparent',
                color: '#ef4444', fontSize: 14, fontWeight: 600, cursor: 'pointer',
              }}
            >
              Log Out
            </button>
          </div>

        </div>
      </div>
    </div>
  )
}
