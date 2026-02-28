import { useState } from 'react'
import MapView from '../components/MapView'
import ZonePanel from '../components/ZonePanel'
import LeadPinPanel from '../components/LeadPinPanel'
import RecommendationCard from '../components/RecommendationCard'
import RoutePanel from '../components/RoutePanel'
import ErrorBoundary from '../components/ErrorBoundary'
import FollowUpQueue from '../components/FollowUpQueue'
import TeamPanel from '../components/TeamPanel'
import LeaderboardPanel from '../components/LeaderboardPanel'
import useAppStore from '../stores/appStore'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { useDarkMode } from '../hooks/useDarkMode'
import { useOfflineQueue } from '../hooks/useOfflineQueue'
import { useServiceWorker } from '../hooks/useServiceWorker'

type MobileTab = 'map' | 'zones' | 'route'

function Dashboard() {
  const logout = useAppStore((s) => s.logout)
  const user = useAppStore((s) => s.user)
  const isMobile = useMediaQuery('(max-width: 767px)')
  const [mobileTab, setMobileTab] = useState<MobileTab>('map')

  const selectedLeadPinId = useAppStore((s) => s.selectedLeadPinId)

  const { darkMode, toggleDarkMode } = useDarkMode()
  const { isOnline, pendingCount } = useOfflineQueue()
  const { needsUpdate, update: updateSW } = useServiceWorker()

  if (isMobile) {
    return (
      <div
        style={{
          display: 'flex', flexDirection: 'column', height: '100dvh',
          fontFamily: 'system-ui, -apple-system, sans-serif',
          background: 'var(--bg-primary)', color: 'var(--text-primary)',
        }}
      >
        {/* SW update banner */}
        {needsUpdate && (
          <div
            style={{
              background: 'var(--accent-blue)', color: '#fff',
              padding: '6px 12px', fontSize: 12, display: 'flex',
              justifyContent: 'space-between', alignItems: 'center',
            }}
          >
            <span>Update available</span>
            <button
              onClick={updateSW}
              style={{
                background: 'rgba(255,255,255,0.2)', border: '1px solid rgba(255,255,255,0.4)',
                borderRadius: 4, padding: '2px 10px', fontSize: 12, color: '#fff',
                cursor: 'pointer', fontWeight: 600,
              }}
            >
              Refresh
            </button>
          </div>
        )}

        {/* Offline banner */}
        {!isOnline && (
          <div
            style={{
              background: '#fef3c7', color: '#92400e',
              padding: '6px 12px', fontSize: 12, display: 'flex',
              justifyContent: 'space-between', alignItems: 'center',
            }}
          >
            <span>You are offline. Changes will sync when reconnected.</span>
            {pendingCount > 0 && (
              <span
                style={{
                  background: '#92400e', color: '#fff', borderRadius: 10,
                  padding: '1px 7px', fontSize: 11, fontWeight: 700,
                }}
              >
                {pendingCount} pending
              </span>
            )}
          </div>
        )}

        {/* Compact header */}
        <div
          style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '8px 12px', borderBottom: '1px solid var(--border-primary)',
            background: 'var(--bg-primary)', minHeight: 44,
          }}
        >
          <span style={{ fontWeight: 700, fontSize: 15, color: 'var(--text-primary)' }}>RoofIQ</span>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <button
              onClick={toggleDarkMode}
              style={{
                background: 'none', border: '1px solid var(--border-primary)', borderRadius: 6,
                padding: '4px 8px', fontSize: 13, cursor: 'pointer', color: 'var(--text-secondary)',
              }}
              title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {darkMode ? 'Light' : 'Dark'}
            </button>
            <button
              onClick={logout}
              style={{
                background: 'none', border: '1px solid var(--border-primary)', borderRadius: 6,
                padding: '4px 10px', fontSize: 13, cursor: 'pointer', color: 'var(--text-secondary)',
              }}
            >
              Logout
            </button>
          </div>
        </div>

        {/* Content area — map, zones, or route */}
        <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
          {/* Map tab */}
          <div
            style={{
              position: 'absolute', inset: 0,
              display: mobileTab === 'map' ? 'block' : 'none',
            }}
          >
            <ErrorBoundary>
              <MapView />
            </ErrorBoundary>
          </div>

          {/* Zones tab */}
          <div
            style={{
              position: 'absolute', inset: 0, background: 'var(--bg-primary)',
              display: mobileTab === 'zones' ? 'flex' : 'none',
              flexDirection: 'column', overflow: 'hidden',
            }}
          >
            {/* RecommendationCard above zone list on mobile */}
            <div style={{ padding: '8px 12px 0', flexShrink: 0 }}>
              <ErrorBoundary>
                <RecommendationCard />
              </ErrorBoundary>
            </div>
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <ZonePanel isMobile />
            </div>
          </div>

          {/* Pin detail overlay — slides up over any tab when a pin is selected */}
          {selectedLeadPinId && (
            <div
              style={{
                position: 'absolute', inset: 0, background: 'var(--bg-primary)',
                zIndex: 50, overflowY: 'auto',
              }}
            >
              <LeadPinPanel />
            </div>
          )}

          {/* Route tab */}
          <div
            style={{
              position: 'absolute', inset: 0, background: 'var(--bg-primary)',
              display: mobileTab === 'route' ? 'flex' : 'none',
              flexDirection: 'column', overflow: 'hidden',
            }}
          >
            <ErrorBoundary>
              <RoutePanel />
            </ErrorBoundary>
          </div>
        </div>

        {/* Bottom tab bar */}
        <div
          style={{
            display: 'flex', borderTop: '1px solid var(--border-primary)',
            background: 'var(--bg-primary)',
            paddingBottom: 'env(safe-area-inset-bottom, 0px)',
          }}
        >
          {/* Map tab button */}
          <button
            onClick={() => setMobileTab('map')}
            style={{
              flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
              gap: 2, padding: '8px 0', border: 'none', background: 'none', cursor: 'pointer',
              color: mobileTab === 'map' ? 'var(--accent-blue)' : 'var(--text-tertiary)',
              fontSize: 11, fontWeight: mobileTab === 'map' ? 600 : 400,
            }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6" />
              <line x1="8" y1="2" x2="8" y2="18" /><line x1="16" y1="6" x2="16" y2="22" />
            </svg>
            Map
          </button>

          {/* Zones tab button */}
          <button
            onClick={() => setMobileTab('zones')}
            style={{
              flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
              gap: 2, padding: '8px 0', border: 'none', background: 'none', cursor: 'pointer',
              color: mobileTab === 'zones' ? 'var(--accent-blue)' : 'var(--text-tertiary)',
              fontSize: 11, fontWeight: mobileTab === 'zones' ? 600 : 400,
            }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" />
              <line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" />
            </svg>
            Zones
          </button>

          {/* Route tab button */}
          <button
            onClick={() => setMobileTab('route')}
            style={{
              flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
              gap: 2, padding: '8px 0', border: 'none', background: 'none', cursor: 'pointer',
              color: mobileTab === 'route' ? 'var(--accent-blue)' : 'var(--text-tertiary)',
              fontSize: 11, fontWeight: mobileTab === 'route' ? 600 : 400,
            }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
            Route
          </button>
        </div>
      </div>
    )
  }

  // Desktop layout
  return (
    <div
      style={{
        display: 'flex', height: '100vh',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        background: 'var(--bg-primary)', color: 'var(--text-primary)',
      }}
    >
      {/* SW update banner — full width at top */}
      {needsUpdate && (
        <div
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, zIndex: 1000,
            background: 'var(--accent-blue)', color: '#fff',
            padding: '6px 16px', fontSize: 13, display: 'flex',
            justifyContent: 'space-between', alignItems: 'center',
          }}
        >
          <span>Update available — refresh to get the latest version.</span>
          <button
            onClick={updateSW}
            style={{
              background: 'rgba(255,255,255,0.2)', border: '1px solid rgba(255,255,255,0.4)',
              borderRadius: 4, padding: '3px 12px', fontSize: 12, color: '#fff',
              cursor: 'pointer', fontWeight: 600,
            }}
          >
            Refresh
          </button>
        </div>
      )}

      {/* Offline banner — full width at top */}
      {!isOnline && (
        <div
          style={{
            position: 'fixed', top: needsUpdate ? 36 : 0, left: 0, right: 0, zIndex: 999,
            background: '#fef3c7', color: '#92400e',
            padding: '6px 16px', fontSize: 13, display: 'flex',
            justifyContent: 'space-between', alignItems: 'center',
          }}
        >
          <span>You are offline. Changes will sync when reconnected.</span>
          {pendingCount > 0 && (
            <span
              style={{
                background: '#92400e', color: '#fff', borderRadius: 10,
                padding: '1px 8px', fontSize: 11, fontWeight: 700,
              }}
            >
              {pendingCount} pending
            </span>
          )}
        </div>
      )}

      {/* Map — fills remaining space */}
      <div style={{ flex: 1 }}>
        <ErrorBoundary>
          <MapView />
        </ErrorBoundary>
      </div>

      {/* Right sidebar */}
      <div
        style={{
          width: 380, minWidth: 340,
          borderLeft: '1px solid var(--border-primary)',
          overflow: 'hidden', background: 'var(--bg-primary)',
          display: 'flex', flexDirection: 'column',
        }}
      >
        {/* Sidebar header */}
        <div
          style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '12px 16px', borderBottom: '1px solid var(--border-primary)',
            flexShrink: 0,
          }}
        >
          <span style={{ fontWeight: 700, fontSize: 16, color: 'var(--text-primary)' }}>RoofIQ</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {user && (
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{user.email}</span>
            )}
            <button
              onClick={toggleDarkMode}
              style={{
                background: 'none', border: '1px solid var(--border-primary)', borderRadius: 6,
                padding: '4px 8px', fontSize: 12, cursor: 'pointer', color: 'var(--text-secondary)',
              }}
              title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {darkMode ? 'Light' : 'Dark'}
            </button>
            <button
              onClick={logout}
              style={{
                background: 'none', border: '1px solid var(--border-primary)', borderRadius: 6,
                padding: '4px 10px', fontSize: 13, cursor: 'pointer', color: 'var(--text-secondary)',
              }}
            >
              Logout
            </button>
          </div>
        </div>

        {/* Sidebar body — scrollable */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {selectedLeadPinId ? (
            /* Pin detail takes over the sidebar when a pin is selected */
            <div style={{ flex: 1, overflowY: 'auto' }}>
              <LeadPinPanel />
            </div>
          ) : (
            <>
              {/* RecommendationCard above the zone panel */}
              <div style={{ padding: '10px 12px 0', flexShrink: 0 }}>
                <ErrorBoundary>
                  <RecommendationCard />
                </ErrorBoundary>
              </div>

              {/* Team panel */}
              <div style={{ flexShrink: 0 }}>
                <ErrorBoundary>
                  <TeamPanel />
                </ErrorBoundary>
              </div>

              {/* Leaderboard panel */}
              <div style={{ flexShrink: 0 }}>
                <ErrorBoundary>
                  <LeaderboardPanel />
                </ErrorBoundary>
              </div>

              {/* Follow-up queue */}
              <div style={{ flexShrink: 0 }}>
                <ErrorBoundary>
                  <FollowUpQueue />
                </ErrorBoundary>
              </div>

              {/* Zone panel fills remaining space */}
              <div style={{ flex: 1, overflow: 'hidden' }}>
                <ZonePanel />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default Dashboard
