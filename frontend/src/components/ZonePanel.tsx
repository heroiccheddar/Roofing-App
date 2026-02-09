import useAppStore from '../stores/appStore'
import { useZoneList, useZoneDetail } from '../hooks/useZones'
import type { ZoneResponse } from '../types/api'

function ZonePanel() {
  const selectedZoneId = useAppStore((s) => s.selectedZoneId)
  const setSelectedZoneId = useAppStore((s) => s.setSelectedZoneId)
  const minScore = useAppStore((s) => s.filters.minScore)
  const setFilters = useAppStore((s) => s.setFilters)
  const { data: zoneList, isLoading: listLoading } = useZoneList()
  const { data: detail } = useZoneDetail(selectedZoneId)

  // If a zone is selected, show detail view
  if (selectedZoneId && detail) {
    return (
      <div style={styles.panel}>
        <button onClick={() => setSelectedZoneId(null)} style={styles.backBtn}>
          ← Back to list
        </button>
        <h2 style={styles.heading}>Zone Detail</h2>
        <div style={styles.scoreCard}>
          <span style={{
            ...styles.scoreBadge,
            background: BAND_BG[detail.score_band] || '#f1f5f9',
            color: BAND_COLOR[detail.score_band] || '#64748b',
          }}>
            {detail.score_band.toUpperCase()}
          </span>
          <span style={styles.scoreValue}>{detail.decay_adjusted_score.toFixed(1)}</span>
        </div>
        <div style={styles.statGrid}>
          <Stat label="Damage Prob" value={detail.damage_prob.toFixed(1)} />
          <Stat label="Lead Quality" value={detail.lead_quality.toFixed(1)} />
          <Stat label="Density Bonus" value={detail.density_bonus.toFixed(1)} />
          <Stat label="Events" value={String(detail.event_count)} />
          <Stat label="Max Hail" value={detail.max_hail_diameter ? `${detail.max_hail_diameter}"` : 'N/A'} />
          <Stat label="Max Wind" value={detail.max_wind_speed ? `${detail.max_wind_speed} mph` : 'N/A'} />
          <Stat label="Hours Ago" value={detail.hours_since_storm.toFixed(1)} />
          <Stat label="Conversion" value={detail.predicted_conversion_rate ? `${(detail.predicted_conversion_rate * 100).toFixed(0)}%` : 'N/A'} />
        </div>
        {detail.events.length > 0 && (
          <>
            <h3 style={{ marginTop: 16, marginBottom: 8 }}>Storm Events</h3>
            {detail.events.map((evt) => (
              <div key={evt.id} style={styles.eventCard}>
                <span style={styles.eventSource}>{evt.source.toUpperCase()}</span>
                <span>{evt.event_type}</span>
                {evt.hail_diameter && <span>{evt.hail_diameter}" hail</span>}
                {evt.wind_speed && <span>{evt.wind_speed} mph</span>}
              </div>
            ))}
          </>
        )}
      </div>
    )
  }

  // Zone list view
  return (
    <div style={styles.panel}>
      <h2 style={styles.heading}>Lead Zones</h2>
      <div style={styles.filterRow}>
        <label style={{ fontSize: 13, color: '#64748b' }}>Min Score: {minScore}</label>
        <input
          type="range"
          min={0} max={100}
          value={minScore}
          onChange={(e) => setFilters({ minScore: Number(e.target.value) })}
          style={{ width: '100%' }}
        />
      </div>
      {listLoading && <p style={{ color: '#64748b' }}>Loading zones...</p>}
      {zoneList?.zones.map((zone: ZoneResponse) => (
        <div
          key={zone.id}
          onClick={() => setSelectedZoneId(zone.id)}
          style={styles.zoneCard}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{
              ...styles.scoreBadge,
              background: BAND_BG[zone.score_band] || '#f1f5f9',
              color: BAND_COLOR[zone.score_band] || '#64748b',
            }}>
              {zone.score_band.toUpperCase()} {zone.composite_score.toFixed(0)}
            </span>
            <span style={{ fontSize: 12, color: '#94a3b8' }}>
              {zone.event_count} event{zone.event_count !== 1 ? 's' : ''}
            </span>
          </div>
          <div style={{ marginTop: 4, fontSize: 13, color: '#475569' }}>
            {zone.max_hail_diameter ? `${zone.max_hail_diameter}" hail` : ''}
            {zone.max_hail_diameter && zone.max_wind_speed ? ' · ' : ''}
            {zone.max_wind_speed ? `${zone.max_wind_speed} mph wind` : ''}
          </div>
        </div>
      ))}
      {zoneList && zoneList.zones.length === 0 && (
        <p style={{ color: '#94a3b8', textAlign: 'center', marginTop: 32 }}>
          No zones found in your service area
        </p>
      )}
    </div>
  )
}

// Helper component
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ padding: 8 }}>
      <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#0f172a' }}>{value}</div>
    </div>
  )
}

const BAND_BG: Record<string, string> = {
  hot: '#fef2f2', warm: '#fff7ed', cool: '#fefce8', skip: '#f1f5f9',
}
const BAND_COLOR: Record<string, string> = {
  hot: '#dc2626', warm: '#ea580c', cool: '#ca8a04', skip: '#64748b',
}

const styles: Record<string, React.CSSProperties> = {
  panel: { padding: 16 },
  heading: { margin: '0 0 16px', fontSize: 20, fontWeight: 700, color: '#0f172a' },
  backBtn: {
    background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer',
    fontSize: 14, padding: 0, marginBottom: 8,
  },
  scoreCard: {
    display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16,
  },
  scoreBadge: {
    padding: '4px 10px', borderRadius: 6, fontSize: 13, fontWeight: 600,
  },
  scoreValue: { fontSize: 32, fontWeight: 700, color: '#0f172a' },
  statGrid: {
    display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4,
    background: '#f8fafc', borderRadius: 8, padding: 8,
  },
  filterRow: { marginBottom: 16 },
  zoneCard: {
    padding: 12, marginBottom: 8, borderRadius: 8, border: '1px solid #e2e8f0',
    cursor: 'pointer', transition: 'background 0.15s',
  },
  eventCard: {
    display: 'flex', gap: 8, alignItems: 'center', padding: '6px 0',
    fontSize: 13, color: '#475569', borderBottom: '1px solid #f1f5f9',
  },
  eventSource: {
    fontSize: 11, fontWeight: 600, padding: '2px 6px', borderRadius: 4,
    background: '#f1f5f9', color: '#475569',
  },
}

export default ZonePanel
