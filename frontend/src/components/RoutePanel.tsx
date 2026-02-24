import { useEffect } from 'react'
import { useGeolocation } from '../hooks/useGeolocation'
import { useRoutePlanner } from '../hooks/useRoute'
import useAppStore from '../stores/appStore'
import { useZoneList } from '../hooks/useZones'

/**
 * Route planning panel.
 *
 * Reads selected zones from store, allows building an ordered route,
 * and pushes the resulting geometry back into the store for MapView to render.
 */
function RoutePanel() {
  const routeZoneIds = useAppStore((s) => s.routeZoneIds)
  const toggleZoneInRoute = useAppStore((s) => s.toggleZoneInRoute)
  const setRouteGeometry = useAppStore((s) => s.setRouteGeometry)
  const clearRoute = useAppStore((s) => s.clearRoute)

  const { lat, lon, loading: geoLoading } = useGeolocation()
  const { mutate, isPending, data: routeData, error: routeError, reset } = useRoutePlanner()
  const { data: zoneList } = useZoneList()

  // Push geometry to store whenever route data arrives
  useEffect(() => {
    if (routeData?.geometry) {
      setRouteGeometry(routeData.geometry)
    }
  }, [routeData, setRouteGeometry])

  // Build a lookup from zoneId to display_name
  const zoneNames: Record<string, string> = {}
  if (zoneList?.zones) {
    for (const z of zoneList.zones) {
      zoneNames[z.id] = z.display_name || z.h3_index.slice(0, 8)
    }
  }

  const canPlan = routeZoneIds.length >= 2 && lat !== null && !geoLoading

  function handlePlanRoute() {
    if (!canPlan) return
    reset()
    mutate({
      zone_ids: routeZoneIds,
      start_lat: lat!,
      start_lon: lon!,
    })
  }

  function handleClearRoute() {
    reset()
    clearRoute()
  }

  return (
    <div
      style={{
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      <h2
        style={{
          margin: '0 0 12px',
          fontSize: 18,
          fontWeight: 700,
          color: 'var(--text-primary)',
        }}
      >
        Route Planner
      </h2>

      {/* No zones selected */}
      {routeZoneIds.length === 0 && (
        <div
          style={{
            padding: 16,
            borderRadius: 8,
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-primary)',
            color: 'var(--text-secondary)',
            fontSize: 13,
            textAlign: 'center',
          }}
        >
          Add zones to your route from the Zones list or Recommendations panel.
          <br />
          <span style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4, display: 'block' }}>
            Select at least 2 zones to plan a route.
          </span>
        </div>
      )}

      {/* Zone list */}
      {routeZoneIds.length > 0 && (
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0, marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 8 }}>
            {routeZoneIds.length} zone{routeZoneIds.length !== 1 ? 's' : ''} selected (max 10)
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {routeZoneIds.map((zoneId, index) => {
              // Find waypoint order in planned route if available
              const waypoint = routeData?.waypoints.find((w) => w.zone_id === zoneId)
              const label = waypoint?.display_name || zoneNames[zoneId] || zoneId.slice(0, 8)

              return (
                <div
                  key={zoneId}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '8px 10px',
                    borderRadius: 8,
                    border: '1px solid var(--border-primary)',
                    background: 'var(--card-bg)',
                    minHeight: 44,
                  }}
                >
                  {/* Order number */}
                  <span
                    style={{
                      width: 22,
                      height: 22,
                      borderRadius: '50%',
                      background: 'var(--accent-blue)',
                      color: '#fff',
                      fontSize: 11,
                      fontWeight: 700,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    {waypoint ? waypoint.order + 1 : index + 1}
                  </span>

                  {/* Zone name */}
                  <span
                    style={{
                      flex: 1,
                      fontSize: 13,
                      color: 'var(--text-primary)',
                      fontWeight: 500,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {label}
                  </span>

                  {/* Remove button */}
                  <button
                    onClick={() => toggleZoneInRoute(zoneId)}
                    style={{
                      padding: '4px 8px',
                      borderRadius: 4,
                      border: 'none',
                      background: 'var(--bg-tertiary)',
                      color: 'var(--text-secondary)',
                      fontSize: 12,
                      cursor: 'pointer',
                      flexShrink: 0,
                      minHeight: 28,
                    }}
                    title="Remove from route"
                  >
                    Remove
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Route summary after planning */}
      {routeData && (
        <div
          style={{
            padding: 10,
            borderRadius: 8,
            background: 'var(--success-bg)',
            color: 'var(--success-text)',
            fontSize: 13,
            marginBottom: 10,
            border: '1px solid var(--accent-green)',
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Route planned</div>
          <div style={{ display: 'flex', gap: 16 }}>
            <span>
              {routeData.total_distance_km.toFixed(1)} km
            </span>
            <span>
              ~{Math.round(routeData.total_duration_minutes)} min
            </span>
            <span>
              {routeData.waypoints.length} stops
            </span>
          </div>
        </div>
      )}

      {/* Error */}
      {routeError && (
        <div
          style={{
            padding: 10,
            borderRadius: 8,
            background: 'var(--error-bg)',
            color: 'var(--error-text)',
            fontSize: 13,
            marginBottom: 10,
          }}
        >
          Route error: {routeError.message}
        </div>
      )}

      {/* GPS status */}
      {geoLoading && (
        <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
          Waiting for GPS...
        </p>
      )}
      {!geoLoading && lat === null && (
        <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>
          GPS unavailable — enable location to plan a route.
        </p>
      )}

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          onClick={handlePlanRoute}
          disabled={!canPlan || isPending}
          style={{
            flex: 1,
            padding: '10px 0',
            borderRadius: 8,
            border: 'none',
            background: canPlan && !isPending ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
            color: canPlan && !isPending ? '#fff' : 'var(--text-tertiary)',
            fontSize: 14,
            fontWeight: 600,
            cursor: canPlan && !isPending ? 'pointer' : 'not-allowed',
            minHeight: 44,
          }}
        >
          {isPending ? 'Planning...' : 'Plan Route'}
        </button>

        {(routeZoneIds.length > 0 || routeData) && (
          <button
            onClick={handleClearRoute}
            style={{
              padding: '10px 16px',
              borderRadius: 8,
              border: '1px solid var(--border-primary)',
              background: 'var(--bg-secondary)',
              color: 'var(--text-secondary)',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              minHeight: 44,
            }}
          >
            Clear
          </button>
        )}
      </div>
    </div>
  )
}

export default RoutePanel
