/**
 * Neighborhood breakdown showing census tracts ranked by canvass priority.
 *
 * Fetches tract GeoJSON for a zone and renders each tract as a card with
 * demographics, building data, risk exposure, and market intelligence.
 */
import { useState } from 'react'
import useAppStore from '../stores/appStore'
import { useZoneTracts, useTractProperties } from '../hooks/useZones'
import { ZoneCardSkeleton } from './SkeletonLoader'
import type { PropertyResponse } from '../types/api'

interface TractProperties {
  geoid: string
  canvass_priority: number
  // Housing stock
  owner_occupied_pct: number | null
  single_family_pct: number | null
  pct_built_before_1980: number | null
  median_home_value: number | null
  median_year_built: number | null
  building_count: number | null
  dominant_decade: string | null
  dominant_decade_pct: number | null
  age_clustering_score: number | null
  avg_building_area_sqm: number | null
  // Demographics & market
  population: number | null
  housing_units: number | null
  median_household_income: number | null
  vacancy_rate: number | null
  pct_cost_burdened: number | null
  hpi_5yr_change: number | null
  // Storm & risk exposure
  hail_exposure_score: number | null
  hail_events_3yr: number | null
  max_hail_diameter_3yr: number | null
  tree_canopy_mean_pct: number | null
  tree_canopy_risk_score: number | null
  climate_weathering_score: number | null
  freeze_thaw_days: number | null
  fema_disaster_count: number | null
  fema_disaster_score: number | null
  nri_hail_riskr: string | null
  nri_swnd_riskr: string | null
  nri_trnd_riskr: string | null
  // Real estate market
  redfin_median_sale_price: number | null
  redfin_median_dom: number | null
  redfin_price_drop_pct: number | null
  // Flood risk
  flood_risk_category: string | null
  flood_insurance_required: boolean | null
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

function fmtPct(val: number | null): string {
  if (val == null) return '-'
  return `${val.toFixed(0)}%`
}

function fmtDollar(val: number | null): string {
  if (val == null) return '-'
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`
  if (val >= 1_000) return `$${(val / 1_000).toFixed(0)}k`
  return `$${val.toFixed(0)}`
}

function fmtNum(val: number | null, suffix = ''): string {
  if (val == null) return '-'
  return `${val.toLocaleString()}${suffix}`
}

function riskColor(risk: string | null): { bg: string; fg: string } {
  if (!risk) return { bg: 'var(--bg-secondary)', fg: 'var(--text-tertiary)' }
  const r = risk.toLowerCase()
  if (r.startsWith('very h')) return { bg: '#fef2f2', fg: '#dc2626' }
  if (r.startsWith('rel') && r.includes('high')) return { bg: '#fff7ed', fg: '#ea580c' }
  if (r.startsWith('rel') && r.includes('mod')) return { bg: '#fefce8', fg: '#ca8a04' }
  if (r.startsWith('rel') && r.includes('low')) return { bg: '#eff6ff', fg: '#2563eb' }
  if (r.startsWith('very l')) return { bg: '#f0fdf4', fg: '#16a34a' }
  return { bg: 'var(--bg-secondary)', fg: 'var(--text-tertiary)' }
}

function floodColor(category: string | null): { bg: string; fg: string } {
  if (!category) return { bg: 'var(--bg-secondary)', fg: 'var(--text-tertiary)' }
  const c = category.toLowerCase()
  if (c === 'high') return { bg: '#fef2f2', fg: '#dc2626' }
  if (c === 'moderate') return { bg: '#fff7ed', fg: '#ea580c' }
  if (c === 'low') return { bg: '#fefce8', fg: '#ca8a04' }
  return { bg: '#f0fdf4', fg: '#16a34a' }
}

function MiniBar({ value, max = 100, color = '#2563eb' }: { value: number | null; max?: number; color?: string }) {
  if (value == null) return <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>-</span>
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ flex: 1, height: 6, borderRadius: 3, background: 'var(--bg-tertiary)' }}>
        <div style={{ width: `${pct}%`, height: '100%', borderRadius: 3, background: color, transition: 'width 0.3s' }} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', minWidth: 28, textAlign: 'right' }}>
        {value.toFixed(0)}
      </span>
    </div>
  )
}

function RiskBadge({ label, risk }: { label: string; risk: string | null }) {
  const colors = riskColor(risk)
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '2px 0' }}>
      <span style={{ fontSize: 11, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>{label}</span>
      <span style={{
        fontSize: 10, fontWeight: 600, padding: '2px 6px', borderRadius: 4,
        background: colors.bg, color: colors.fg,
      }}>
        {risk || 'N/A'}
      </span>
    </div>
  )
}

function SectionToggle({ label, open, onToggle }: { label: string; open: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%',
        padding: '6px 0', border: 'none', background: 'none', cursor: 'pointer',
        borderTop: '1px solid var(--border-primary)', marginTop: 6,
      }}
    >
      <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {label}
      </span>
      <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>{open ? '▾' : '▸'}</span>
    </button>
  )
}

function TractCard({ p, isFocused, onFocus, zoneId }: { p: TractProperties; isFocused: boolean; onFocus: () => void; zoneId: string }) {
  const [showRisk, setShowRisk] = useState(false)
  const [showMarket, setShowMarket] = useState(false)
  const [showProperties, setShowProperties] = useState(false)
  const colors = priorityColor(p.canvass_priority)

  const hasRisk = p.hail_exposure_score != null || p.tree_canopy_risk_score != null ||
    p.fema_disaster_count != null || p.nri_hail_riskr != null || p.climate_weathering_score != null
  const hasMarket = p.redfin_median_sale_price != null || p.median_household_income != null ||
    p.vacancy_rate != null || p.hpi_5yr_change != null

  return (
    <div
      style={{
        background: isFocused ? 'var(--bg-tertiary)' : 'var(--card-bg)',
        border: `1px solid ${isFocused ? 'var(--accent-blue)' : 'var(--border-primary)'}`,
        borderRadius: 8, padding: 12, marginBottom: 8,
        transition: 'border-color 0.2s',
      }}
    >
      {/* Header */}
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
          onClick={onFocus}
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

      {/* Housing Stock — always visible */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 4 }}>
        <TractStat label="Owner Occ." value={fmtPct(p.owner_occupied_pct)} />
        <TractStat label="Single Fam." value={fmtPct(p.single_family_pct)} />
        <TractStat label="Pre-1980" value={fmtPct(p.pct_built_before_1980)} />
        <TractStat label="Buildings" value={fmtNum(p.building_count)} />
        <TractStat label="Home Value" value={fmtDollar(p.median_home_value)} />
        <TractStat label="Built Era" value={p.dominant_decade ? `${p.dominant_decade}${p.dominant_decade_pct ? ` (${p.dominant_decade_pct.toFixed(0)}%)` : ''}` : '-'} />
        {p.population != null && <TractStat label="Population" value={fmtNum(p.population)} />}
        {p.housing_units != null && <TractStat label="Housing Units" value={fmtNum(p.housing_units)} />}
        {p.avg_building_area_sqm != null && <TractStat label="Avg Bldg Size" value={`${Math.round(p.avg_building_area_sqm * 10.764)} ft²`} />}
      </div>

      {/* Storm & Risk Exposure — collapsible */}
      {hasRisk && (
        <>
          <SectionToggle label="Storm & Risk" open={showRisk} onToggle={() => setShowRisk(!showRisk)} />
          {showRisk && (
            <div style={{ padding: '4px 0' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 6 }}>
                {p.hail_exposure_score != null && (
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: 2 }}>Hail Exposure</div>
                    <MiniBar value={p.hail_exposure_score} color={p.hail_exposure_score >= 60 ? '#dc2626' : p.hail_exposure_score >= 30 ? '#ea580c' : '#2563eb'} />
                  </div>
                )}
                {p.tree_canopy_risk_score != null && (
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: 2 }}>Tree Risk</div>
                    <MiniBar value={p.tree_canopy_risk_score} color={p.tree_canopy_risk_score >= 60 ? '#dc2626' : '#ea580c'} />
                  </div>
                )}
                {p.climate_weathering_score != null && (
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: 2 }}>Climate Wear</div>
                    <MiniBar value={p.climate_weathering_score} color="#6366f1" />
                  </div>
                )}
                {p.fema_disaster_score != null && (
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: 2 }}>FEMA Disasters</div>
                    <MiniBar value={p.fema_disaster_score} color="#dc2626" />
                  </div>
                )}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 4 }}>
                {p.hail_events_3yr != null && <TractStat label="Hail Events (3yr)" value={fmtNum(p.hail_events_3yr)} />}
                {p.max_hail_diameter_3yr != null && <TractStat label="Max Hail" value={`${p.max_hail_diameter_3yr.toFixed(2)}"`} />}
                {p.tree_canopy_mean_pct != null && <TractStat label="Tree Cover" value={fmtPct(p.tree_canopy_mean_pct)} />}
                {p.freeze_thaw_days != null && <TractStat label="Freeze/Thaw" value={`${p.freeze_thaw_days.toFixed(0)} days`} />}
                {p.fema_disaster_count != null && <TractStat label="FEMA Events" value={fmtNum(p.fema_disaster_count)} />}
                {p.flood_risk_category != null && (
                  <div style={{ padding: '4px 6px' }}>
                    <div style={{ fontSize: 10, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>Flood Risk</div>
                    <span style={{
                      fontSize: 12, fontWeight: 600, padding: '1px 5px', borderRadius: 4,
                      ...floodColor(p.flood_risk_category),
                    }}>
                      {p.flood_risk_category}{p.flood_insurance_required ? ' *' : ''}
                    </span>
                  </div>
                )}
              </div>
              {(p.nri_hail_riskr || p.nri_swnd_riskr || p.nri_trnd_riskr) && (
                <div style={{ marginTop: 4 }}>
                  <RiskBadge label="Hail" risk={p.nri_hail_riskr} />
                  <RiskBadge label="Wind" risk={p.nri_swnd_riskr} />
                  <RiskBadge label="Tornado" risk={p.nri_trnd_riskr} />
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* Market Intelligence — collapsible */}
      {hasMarket && (
        <>
          <SectionToggle label="Market Intel" open={showMarket} onToggle={() => setShowMarket(!showMarket)} />
          {showMarket && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 4, padding: '4px 0' }}>
              {p.median_household_income != null && <TractStat label="Median Income" value={fmtDollar(p.median_household_income)} />}
              {p.vacancy_rate != null && <TractStat label="Vacancy" value={fmtPct(p.vacancy_rate)} />}
              {p.pct_cost_burdened != null && <TractStat label="Cost Burdened" value={fmtPct(p.pct_cost_burdened)} />}
              {p.hpi_5yr_change != null && <TractStat label="HPI 5yr" value={`${p.hpi_5yr_change > 0 ? '+' : ''}${p.hpi_5yr_change.toFixed(1)}%`} />}
              {p.age_clustering_score != null && <TractStat label="Age Cluster" value={p.age_clustering_score.toFixed(0)} />}
              {p.redfin_median_sale_price != null && <TractStat label="Sale Price" value={fmtDollar(p.redfin_median_sale_price)} />}
              {p.redfin_median_dom != null && <TractStat label="Days on Mkt" value={fmtNum(p.redfin_median_dom)} />}
              {p.redfin_price_drop_pct != null && <TractStat label="Price Drops" value={fmtPct(p.redfin_price_drop_pct)} />}
            </div>
          )}
        </>
      )}

      {/* Properties — loads on expand */}
      <SectionToggle label="Properties" open={showProperties} onToggle={() => setShowProperties(!showProperties)} />
      {showProperties && <PropertyList zoneId={zoneId} tractGeoid={p.geoid} />}
    </div>
  )
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
        const isFocused = focusedTractId === p.geoid
        return (
          <TractCard
            key={p.geoid}
            p={p}
            isFocused={isFocused}
            onFocus={() => setFocusedTractId(isFocused ? null : p.geoid)}
            zoneId={zoneId}
          />
        )
      })}
    </div>
  )
}

function roofAgeBadge(age: number | undefined | null): { bg: string; fg: string; label: string } {
  if (age == null) return { bg: 'var(--bg-secondary)', fg: 'var(--text-tertiary)', label: 'Unknown' }
  if (age >= 25) return { bg: '#fef2f2', fg: '#dc2626', label: `${age}yr` }
  if (age >= 15) return { bg: '#fff7ed', fg: '#ea580c', label: `${age}yr` }
  return { bg: '#f0fdf4', fg: '#16a34a', label: `${age}yr` }
}

function PropertyList({ zoneId, tractGeoid }: { zoneId: string; tractGeoid: string }) {
  const [sortBy, setSortBy] = useState('year_built')
  const { data, isLoading, error } = useTractProperties(zoneId, tractGeoid, sortBy)

  if (isLoading) {
    return (
      <div style={{ padding: '8px 0' }}>
        <div style={{ height: 14, background: 'var(--bg-tertiary)', borderRadius: 4, marginBottom: 8, width: '60%' }} />
        {[1, 2, 3].map(i => (
          <div key={i} style={{ height: 72, background: 'var(--bg-tertiary)', borderRadius: 6, marginBottom: 6 }} />
        ))}
      </div>
    )
  }

  if (error) return <p style={{ color: '#dc2626', fontSize: 12, padding: '4px 0' }}>Failed to load properties</p>
  if (!data?.has_county_adapter) return <p style={{ color: 'var(--text-tertiary)', fontSize: 12, padding: '4px 0' }}>Property data not available for this county</p>
  if (!data || data.properties.length === 0) return <p style={{ color: 'var(--text-tertiary)', fontSize: 12, padding: '4px 0' }}>No properties found</p>

  return (
    <div style={{ padding: '4px 0' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
          {data.total} properties · {data.source_county} County
        </span>
        <div style={{ display: 'flex', gap: 4 }}>
          {(['year_built', 'assessed_value', 'address'] as const).map(s => (
            <button
              key={s}
              onClick={() => setSortBy(s)}
              style={{
                fontSize: 10, padding: '2px 6px', borderRadius: 4, cursor: 'pointer',
                border: `1px solid ${sortBy === s ? 'var(--accent-blue)' : 'var(--border-primary)'}`,
                background: sortBy === s ? 'var(--accent-blue)' : 'transparent',
                color: sortBy === s ? '#fff' : 'var(--text-secondary)',
              }}
            >
              {s === 'year_built' ? 'Age' : s === 'assessed_value' ? 'Value' : 'A-Z'}
            </button>
          ))}
        </div>
      </div>
      {data.properties.map(prop => <PropertyCard key={prop.id} property={prop} />)}
      {data.total > data.properties.length && (
        <p style={{ fontSize: 11, color: 'var(--text-tertiary)', textAlign: 'center', padding: 4 }}>
          Showing {data.properties.length} of {data.total}
        </p>
      )}
    </div>
  )
}

function PropertyCard({ property: p }: { property: PropertyResponse }) {
  const badge = roofAgeBadge(p.estimated_roof_age)
  return (
    <div style={{
      background: 'var(--bg-secondary)', borderRadius: 6, padding: '8px 10px', marginBottom: 4,
      borderLeft: p.estimated_roof_age != null && p.estimated_roof_age >= 25
        ? '3px solid #dc2626'
        : p.estimated_roof_age != null && p.estimated_roof_age >= 15
          ? '3px solid #ea580c'
          : '3px solid var(--border-primary)',
    }}>
      {/* Row 1: Address + roof age badge */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', flex: 1 }}>
          {p.address || 'No address'}
        </span>
        <span style={{
          fontSize: 10, fontWeight: 600, padding: '1px 6px', borderRadius: 4, marginLeft: 8,
          background: badge.bg, color: badge.fg, whiteSpace: 'nowrap',
        }}>
          {badge.label}
        </span>
      </div>

      {/* Row 2: Owner */}
      {p.owner_name && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
          {p.owner_name}
        </div>
      )}

      {/* Row 3: Stats */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {p.year_built != null && <MiniStat label="Built" value={String(p.year_built)} />}
        {p.assessed_value != null && <MiniStat label="Value" value={fmtDollar(p.assessed_value)} />}
        {p.square_footage != null && <MiniStat label="SqFt" value={p.square_footage.toLocaleString()} />}
        {p.lot_size_acres != null && <MiniStat label="Lot" value={`${p.lot_size_acres.toFixed(2)} ac`} />}
        {p.bedrooms != null && <MiniStat label="Bed" value={String(p.bedrooms)} />}
        {p.bathrooms != null && <MiniStat label="Bath" value={String(p.bathrooms)} />}
        {p.zoning && <MiniStat label="Zone" value={p.zoning} />}
      </div>

      {/* Row 4: Last sale */}
      {(p.last_sale_date || p.last_sale_price != null) && (
        <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 3 }}>
          Last sale: {p.last_sale_price != null ? fmtDollar(p.last_sale_price) : ''}
          {p.last_sale_date ? ` on ${p.last_sale_date}` : ''}
        </div>
      )}
    </div>
  )
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <span style={{ fontSize: 11 }}>
      <span style={{ color: 'var(--text-tertiary)' }}>{label} </span>
      <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{value}</span>
    </span>
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
