import { useState } from 'react'
import { useGeolocation } from '../hooks/useGeolocation'
import { useRecommendations } from '../hooks/useRecommendations'
import useAppStore from '../stores/appStore'
import type { RecommendedZone } from '../types/api'

/** Map score_band to a badge background color */
function bandColor(band: string): string {
  switch (band) {
    case 'hot':  return '#ef4444'
    case 'warm': return '#f97316'
    case 'cool': return '#3b82f6'
    case 'skip': return '#94a3b8'
    default:     return '#94a3b8'
  }
}

/** Format distance in km, switching to miles-like display for larger values */
function fmtKm(km: number): string {
  if (km < 1) return `${(km * 1000).toFixed(0)} m`
  if (km < 10) return `${km.toFixed(1)} km`
  return `${km.toFixed(0)} km`
}

/**
 * Collapsible "Where should I go today?" recommendation card.
 *
 * Uses geolocation to determine current position, then fetches the top 5
 * recommended zones from the API ranked by recommendation_score.
 */
function RecommendationCard() {
  const [expanded, setExpanded] = useState(true)
  const [stormOnly, setStormOnly] = useState(false)

  const { lat, lon, error: geoError, loading: geoLoading } = useGeolocation()
  const { data, isLoading, error: queryError } = useRecommendations(lat, lon, 5, stormOnly)

  const setSelectedZoneId = useAppStore((s) => s.setSelectedZoneId)
  const toggleZoneInRoute = useAppStore((s) => s.toggleZoneInRoute)
  const routeZoneIds = useAppStore((s) => s.routeZoneIds)

  return (
    <div
      style={{
        background: 'var(--card-bg)',
        border: '1px solid var(--card-border)',
        borderRadius: 10,
        marginBottom: 12,
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '10px 12px',
          borderBottom: expanded ? '1px solid var(--border-primary)' : 'none',
          cursor: 'pointer',
          minHeight: 44,
        }}
        onClick={() => setExpanded((v) => !v)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
            Where should I go today?
          </span>
          {stormOnly && (
            <span
              style={{
                fontSize: 10,
                fontWeight: 700,
                padding: '2px 6px',
                borderRadius: 4,
                background: '#fff7ed',
                color: '#c2410c',
                border: '1px solid #fdba74',
              }}
            >
              Storm Mode
            </span>
          )}
        </div>
        <span
          style={{
            color: 'var(--text-tertiary)',
            fontSize: 16,
            transition: 'transform 0.2s',
            transform: expanded ? 'rotate(0deg)' : 'rotate(-90deg)',
            display: 'inline-block',
          }}
        >
          &#8964;
        </span>
      </div>

      {/* Body */}
      {expanded && (
        <div style={{ padding: '10px 12px' }}>
          {/* Storm chasing toggle */}
          <div style={{ marginBottom: 10 }}>
            <button
              onClick={() => setStormOnly((v) => !v)}
              style={{
                padding: '6px 12px',
                borderRadius: 6,
                border: '1px solid var(--border-primary)',
                background: stormOnly ? '#c2410c' : 'var(--bg-secondary)',
                color: stormOnly ? '#fff' : 'var(--text-secondary)',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                minHeight: 44,
                width: '100%',
              }}
            >
              {stormOnly ? 'Storm Chasing Mode: ON' : 'Storm Chasing Mode: OFF'}
            </button>
          </div>

          {/* Geolocation loading */}
          {geoLoading && (
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '8px 0' }}>
              Getting your location...
            </p>
          )}

          {/* Geolocation error */}
          {geoError && !geoLoading && (
            <div
              style={{
                padding: 10,
                borderRadius: 6,
                background: 'var(--error-bg)',
                color: 'var(--error-text)',
                fontSize: 13,
              }}
            >
              Location unavailable: {geoError}
            </div>
          )}

          {/* No location yet (no error, just waiting) */}
          {!geoLoading && !geoError && lat === null && (
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '8px 0' }}>
              Enable location to see recommendations.
            </p>
          )}

          {/* Loading recommendations */}
          {lat !== null && isLoading && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="skeleton"
                  style={{
                    height: 64,
                    borderRadius: 8,
                    background: 'var(--skeleton-base)',
                  }}
                />
              ))}
            </div>
          )}

          {/* Query error */}
          {queryError && (
            <div
              style={{
                padding: 10,
                borderRadius: 6,
                background: 'var(--error-bg)',
                color: 'var(--error-text)',
                fontSize: 13,
              }}
            >
              Failed to load recommendations: {(queryError as Error).message}
            </div>
          )}

          {/* Zone list */}
          {data && data.zones.length === 0 && (
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '8px 0', textAlign: 'center' }}>
              No recommendations available right now.
            </p>
          )}

          {data && data.zones.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {data.zones.map((zone: RecommendedZone) => {
                const inRoute = routeZoneIds.includes(zone.zone_id)
                return (
                  <div
                    key={zone.zone_id}
                    onClick={() => setSelectedZoneId(zone.zone_id)}
                    style={{
                      padding: 10,
                      borderRadius: 8,
                      border: '1px solid var(--border-primary)',
                      background: 'var(--bg-secondary)',
                      cursor: 'pointer',
                      minHeight: 44,
                    }}
                  >
                    {/* Top row: badge + score + distance */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          padding: '2px 6px',
                          borderRadius: 4,
                          background: bandColor(zone.score_band),
                          color: '#fff',
                          textTransform: 'uppercase',
                          flexShrink: 0,
                        }}
                      >
                        {zone.score_band}
                      </span>
                      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                        {zone.display_name || 'Zone'}
                      </span>
                      <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--accent-blue)', fontWeight: 500, flexShrink: 0 }}>
                        {fmtKm(zone.distance_km)}
                      </span>
                    </div>

                    {/* Middle row: recommendation score + "Add to Route" */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                        Score: <strong style={{ color: 'var(--text-primary)' }}>{(zone.recommendation_score * 100).toFixed(0)}%</strong>
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          toggleZoneInRoute(zone.zone_id)
                        }}
                        style={{
                          padding: '3px 8px',
                          fontSize: 11,
                          borderRadius: 4,
                          border: 'none',
                          background: inRoute ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
                          color: inRoute ? '#fff' : 'var(--text-secondary)',
                          cursor: 'pointer',
                          fontWeight: 600,
                          minHeight: 28,
                        }}
                      >
                        {inRoute ? '&#10003; Route' : '+ Route'}
                      </button>
                    </div>

                    {/* Reason */}
                    <div style={{ fontSize: 11, color: 'var(--text-tertiary)', lineHeight: 1.4 }}>
                      {zone.reason}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default RecommendationCard
