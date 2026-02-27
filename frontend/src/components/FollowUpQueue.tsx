import { useState } from 'react'
import useAppStore from '../stores/appStore'
import { useLeadPinCallbacks } from '../hooks/useLeadPins'
import { useGeolocation } from '../hooks/useGeolocation'
import { getDirectionsRoute } from '../api/mapbox'
import { DispositionBadge } from './ZoneDetailHelpers'

function callbackTimeLabel(dateStr: string | undefined): { text: string; color: string } {
  if (!dateStr) return { text: 'no date set', color: '#94a3b8' }
  const now = new Date()
  const target = new Date(dateStr)
  const diffMs = target.getTime() - now.getTime()
  const diffHours = diffMs / (1000 * 60 * 60)
  const diffDays = Math.round(diffHours / 24)

  if (diffHours < -24) return { text: `overdue ${Math.abs(diffDays)}d`, color: '#ef4444' }
  if (diffHours < 0) return { text: 'overdue today', color: '#ef4444' }
  if (diffHours < 24) return { text: 'today', color: '#f59e0b' }
  if (diffHours < 48) return { text: 'tomorrow', color: '#22c55e' }
  return { text: `in ${diffDays}d`, color: '#94a3b8' }
}

export default function FollowUpQueue() {
  const darkMode = useAppStore((s) => s.darkMode)
  const setFlyToCoords = useAppStore((s) => s.setFlyToCoords)
  const setSelectedLeadPinId = useAppStore((s) => s.setSelectedLeadPinId)
  const setRouteGeometry = useAppStore((s) => s.setRouteGeometry)
  const clearRoute = useAppStore((s) => s.clearRoute)
  const { data, isLoading } = useLeadPinCallbacks()
  const { lat: geoLat, lon: geoLon, loading: geoLoading } = useGeolocation()

  const [expanded, setExpanded] = useState(true)
  const [routeLoading, setRouteLoading] = useState(false)
  const [routeStats, setRouteStats] = useState<{ distance_km: number; duration_minutes: number; stops: number } | null>(null)
  const [routeError, setRouteError] = useState<string | null>(null)

  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'
  const borderColor = darkMode ? '#334155' : '#e2e8f0'

  const pins = data?.pins ?? []
  const count = pins.length
  const canPlanRoute = count >= 2 && geoLat !== null && geoLon !== null && !geoLoading

  async function handlePlanRoute() {
    if (!canPlanRoute) return
    setRouteLoading(true)
    setRouteError(null)
    try {
      const coords: [number, number][] = [
        [geoLon!, geoLat!],
        ...pins.map((p) => [p.lon, p.lat] as [number, number]),
      ]
      const result = await getDirectionsRoute(coords)
      setRouteGeometry(result.geometry)
      setRouteStats({ distance_km: result.distance_km, duration_minutes: result.duration_minutes, stops: pins.length })
    } catch (err) {
      setRouteError(err instanceof Error ? err.message : 'Route planning failed')
    } finally {
      setRouteLoading(false)
    }
  }

  function handleClearRoute() {
    clearRoute()
    setRouteStats(null)
    setRouteError(null)
  }

  // Auto-collapse if empty
  if (count === 0 && !isLoading) {
    return (
      <div style={{
        padding: '10px 16px',
        borderBottom: `1px solid ${borderColor}`,
        fontSize: 13,
        color: textSecondary,
      }}>
        No follow-ups scheduled
      </div>
    )
  }

  return (
    <div style={{ borderBottom: `1px solid ${borderColor}` }}>
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: textPrimary,
          fontSize: 14,
          fontWeight: 700,
        }}
      >
        <span>Follow-Ups {count > 0 && `(${count})`}</span>
        <span style={{ fontSize: 11, color: textSecondary }}>
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {/* List */}
      {expanded && (
        <>
          <div style={{ maxHeight: 240, overflowY: 'auto' }}>
            {isLoading && (
              <div style={{ padding: 16, fontSize: 13, color: textSecondary, textAlign: 'center' }}>
                Loading...
              </div>
            )}
            {pins.map((pin, i) => {
              const { text, color } = callbackTimeLabel(pin.callback_date)
              return (
                <button
                  key={pin.id}
                  onClick={() => {
                    setFlyToCoords({ lat: pin.lat, lon: pin.lon, zoom: 16 })
                    setSelectedLeadPinId(pin.id)
                  }}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '8px 16px',
                    background: 'transparent',
                    border: 'none',
                    borderTop: `1px solid ${borderColor}`,
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  {/* Stop number when route is active */}
                  {routeStats && (
                    <span style={{
                      width: 20,
                      height: 20,
                      borderRadius: '50%',
                      background: '#2563eb',
                      color: '#fff',
                      fontSize: 10,
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}>
                      {i + 1}
                    </span>
                  )}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: 13,
                      fontWeight: 600,
                      color: textPrimary,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}>
                      {pin.address || 'Dropped pin'}
                    </div>
                    <div style={{ fontSize: 11, color, fontWeight: 600, marginTop: 2 }}>
                      {text}
                    </div>
                    {pin.roofer_name && (
                      <div style={{ fontSize: 11, color: textSecondary, marginTop: 1 }}>
                        by {pin.roofer_name}
                      </div>
                    )}
                  </div>
                  <DispositionBadge disposition={pin.disposition} />
                </button>
              )
            })}
          </div>

          {/* Route stats */}
          {routeStats && (
            <div style={{
              margin: '0 16px 8px',
              padding: 8,
              borderRadius: 8,
              background: darkMode ? '#0c2d1f' : '#f0fdf4',
              border: `1px solid ${darkMode ? '#16a34a44' : '#16a34a33'}`,
              fontSize: 12,
              color: darkMode ? '#4ade80' : '#16a34a',
              fontWeight: 600,
              display: 'flex',
              gap: 12,
            }}>
              <span>{routeStats.distance_km.toFixed(1)} km</span>
              <span>~{Math.round(routeStats.duration_minutes)} min</span>
              <span>{routeStats.stops} stops</span>
            </div>
          )}

          {/* Route error */}
          {routeError && (
            <div style={{
              margin: '0 16px 8px',
              padding: 8,
              borderRadius: 8,
              background: darkMode ? '#2d0c0c' : '#fef2f2',
              border: `1px solid ${darkMode ? '#ef444444' : '#ef444433'}`,
              fontSize: 12,
              color: '#ef4444',
            }}>
              {routeError}
            </div>
          )}

          {/* GPS status */}
          {geoLoading && (
            <div style={{ padding: '4px 16px 8px', fontSize: 11, color: textSecondary }}>
              Waiting for GPS...
            </div>
          )}

          {/* Route buttons */}
          {count >= 2 && (
            <div style={{ display: 'flex', gap: 8, padding: '0 16px 10px' }}>
              {!routeStats ? (
                <button
                  onClick={handlePlanRoute}
                  disabled={!canPlanRoute || routeLoading}
                  style={{
                    flex: 1,
                    padding: '7px 0',
                    borderRadius: 8,
                    border: 'none',
                    background: canPlanRoute && !routeLoading ? '#2563eb' : (darkMode ? '#334155' : '#e2e8f0'),
                    color: canPlanRoute && !routeLoading ? '#fff' : textSecondary,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: canPlanRoute && !routeLoading ? 'pointer' : 'not-allowed',
                  }}
                >
                  {routeLoading ? 'Planning...' : 'Plan Route'}
                </button>
              ) : (
                <button
                  onClick={handleClearRoute}
                  style={{
                    flex: 1,
                    padding: '7px 0',
                    borderRadius: 8,
                    border: `1px solid ${borderColor}`,
                    background: 'transparent',
                    color: textSecondary,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Clear Route
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
