import MapView from '../components/MapView'
import ZonePanel from '../components/ZonePanel'
import useAppStore from '../stores/appStore'

function Dashboard() {
  const logout = useAppStore((s) => s.logout)
  const user = useAppStore((s) => s.user)

  return (
    <div style={{ display: 'flex', height: '100vh', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      {/* Map area - 70% */}
      <div style={{ flex: 1 }}>
        <MapView />
      </div>
      {/* Sidebar - 30% */}
      <div style={{
        width: 380, minWidth: 340,
        borderLeft: '1px solid #e2e8f0',
        overflowY: 'auto', background: '#fff',
        display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '12px 16px', borderBottom: '1px solid #e2e8f0',
        }}>
          <span style={{ fontWeight: 700, fontSize: 16, color: '#0f172a' }}>StormLeads</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {user && <span style={{ fontSize: 13, color: '#64748b' }}>{user.email}</span>}
            <button onClick={logout} style={{
              background: 'none', border: '1px solid #e2e8f0', borderRadius: 6,
              padding: '4px 10px', fontSize: 13, cursor: 'pointer', color: '#64748b',
            }}>
              Logout
            </button>
          </div>
        </div>
        {/* Zone panel */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <ZonePanel />
        </div>
      </div>
    </div>
  )
}

export default Dashboard
