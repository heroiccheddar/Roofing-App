import MapView from '../components/MapView'
import ZonePanel from '../components/ZonePanel'
import AlertFeed from '../components/AlertFeed'

function Dashboard() {
  // TODO: Implement in WP 4.1
  // - Full-screen map with lead zones
  // - Sidebar with zone list and filters
  // - Real-time updates via WebSocket
  // - Score-based color coding
  // - Click zones to see details

  return (
    <div style={{ display: 'flex', height: '100vh' }}>
      <div style={{ flex: 1 }}>
        <MapView />
      </div>
      <div style={{ width: '400px', overflowY: 'auto', padding: '1rem' }}>
        <h1>StormLeads Dashboard</h1>
        <AlertFeed />
        <ZonePanel />
      </div>
    </div>
  )
}

export default Dashboard
