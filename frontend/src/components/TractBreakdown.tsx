/**
 * Neighborhood breakdown showing census tracts ranked by canvass priority.
 *
 * Fetches tract GeoJSON for a zone and renders each tract as a card with
 * demographics, building data, and a "Focus on this area" button.
 */
import useAppStore from '../stores/appStore'
import { useZoneTracts } from '../hooks/useZones'
import { ZoneCardSkeleton } from './SkeletonLoader'

interface TractProperties {
  geoid: string
  canvass_priority: number
  owner_occupied_pct: number | null
  single_family_pct: number | null
  pct_built_before_1980: number | null
  median_home_value: number | null
  median_year_built: number | null
  building_count: number | null
  dominant_decade: string | null
}

function priorityColor(priority: number): { bg: string; fg: string } {
  if (priority >= 80) return { bg: '#fef2f2', fg: '#dc2626' }
  if (priority >= 60) return { bg: '#fff7ed', fg: '#ea580c' }
  if (priority >= 40) return { bg: '#fefce8', fg: '#ca8a04' }
  if (priority >= 20) return { bg: '#eff6ff', fg: '#2563eb' }
  return { bg: '#f1f5f9', fg: '#64748b' }
}

function priorityLabel(priority: number): string {
  if (priority >= 80) return 'High Priority'
  if (priority >= 60) return 'Good'
  if (priority >= 40) return 'Moderate'
  if (priority >= 20) return 'Low'
  return 'Minimal'
}

function formatValue(val: number | null, prefix = '', suffix = ''): string {
  if (val == null) return '-'
  if (prefix === '$') {
    if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`
    if (val >= 1_000) return `$${(val / 1_000).toFixed(0)}k`
    return `$${val.toFixed(0)}`
  }
  return `${prefix}${val.toFixed(0)}${suffix}`
}

export default function TractBreakdown({ zoneId }: { zoneId: string }) {
  const setFocusedTractId = useAppStore((s) => s.setFocusedTractId)
  const focusedTractId = useAppStore((s) => s.focusedTractId)
  const { data, isLoading, error } = useZoneTracts(zoneId)

  if (isLoading) {
    return (
      <div>
        <ZoneCardSkeleton />
        <ZoneCardSkeleton />
        <ZoneCardSkeleton />
      </div>
    )
  }

  if (error) {
    return <p style={{ color: '#dc2626', fontSize: 13 }}>Failed to load tract data</p>
  }

  if (!data || data.features.length === 0) {
    return <p style={{ color: 'var(--text-tertiary)', fontSize: 13 }}>No tract data available for this zone</p>
  }

  const sorted = [...data.features].sort((a, b) => {
    const pa = (a.properties as TractProperties).canvass_priority ?? 0
    const pb = (b.properties as TractProperties).canvass_priority ?? 0
    return pb - pa
  })

  return (
    <div>
      <p style={{ fontSize: 12, color: 'var(--text-tertiary)', margin: '0 0 8px' }}>
        {sorted.length} census tract{sorted.length !== 1 ? 's' : ''} ranked by canvass priority
      </p>
      {sorted.map((feature) => {
        const p = feature.properties as TractProperties
        const colors = priorityColor(p.canvass_priority)
        const isFocused = focusedTractId === p.geoid
        return (
          <div
            key={p.geoid}
            style={{
              background: isFocused ? 'var(--bg-tertiary)' : 'var(--card-bg)',
              border: `1px solid ${isFocused ? 'var(--accent-blue)' : 'var(--border-primary)'}`,
              borderRadius: 8, padding: 12, marginBottom: 8,
              transition: 'border-color 0.2s',
            }}
          >
            {/* Header: priority badge + tract ID + focus button */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{
                fontSize: 12, fontWeight: 600, padding: '3px 8px', borderRadius: 6,
                background: colors.bg, color: colors.fg,
              }}>
                {p.canvass_priority.toFixed(0)} - {priorityLabel(p.canvass_priority)}
              </span>
              <span style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'monospace' }}>
                {p.geoid}
              </span>
              <button
                onClick={() => setFocusedTractId(isFocused ? null : p.geoid)}
                style={{
                  marginLeft: 'auto', fontSize: 11, padding: '3px 8px',
                  border: `1px solid ${isFocused ? 'var(--accent-blue)' : 'var(--border-primary)'}`,
                  borderRadius: 6, cursor: 'pointer',
                  background: isFocused ? 'var(--accent-blue)' : 'transparent',
                  color: isFocused ? '#fff' : 'var(--accent-blue)',
                  fontWeight: 500,
                }}
              >
                {isFocused ? 'Focused' : 'Focus'}
              </button>
            </div>

            {/* Stats grid */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 4 }}>
              <TractStat label="Owner Occ." value={formatValue(p.owner_occupied_pct, '', '%')} />
              <TractStat label="Single Fam." value={formatValue(p.single_family_pct, '', '%')} />
              <TractStat label="Pre-1980" value={formatValue(p.pct_built_before_1980, '', '%')} />
              <TractStat label="Buildings" value={p.building_count != null ? p.building_count.toLocaleString() : '-'} />
              <TractStat label="Home Value" value={formatValue(p.median_home_value, '$')} />
              <TractStat label="Built Era" value={p.dominant_decade || '-'} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function TractStat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ padding: '4px 6px' }}>
      <div style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{value}</div>
    </div>
  )
}
