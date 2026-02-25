/**
 * Neighborhood breakdown showing census tracts ranked by canvass priority.
 *
 * Fetches tract GeoJSON for a zone and renders each tract as a card with
 * demographics, building data, risk exposure, and market intelligence.
 */
import { useState, useMemo } from 'react'
import useAppStore from '../stores/appStore'
import { useZoneTracts, useTractProperties } from '../hooks/useZones'
import { useLeadPins, useDeleteLeadPin, useUpdateLeadPin } from '../hooks/useLeadPins'
import { DispositionBadge } from './ZoneDetailHelpers'
import { DispositionPicker } from './LeadPinPanel'
import { ZoneCardSkeleton } from './SkeletonLoader'
import type { PropertyResponse, LeadPinResponse, LeadPinDisposition } from '../types/api'

interface TractProperties {
  geoid: string
  neighborhood_name: string | null
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
          {p.canvass_priority.toFixed(0)}
        </span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0, flex: 1 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {p.neighborhood_name || priorityLabel(p.canvass_priority)}
          </span>
          <span style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'monospace' }}>
            {p.geoid}
          </span>
        </div>
        <button
          onClick={onFocus}
          style={{
            marginLeft: 'auto', fontSize: 11, padding: '3px 8px',
            border: `1px solid ${isFocused ? 'var(--accent-blue)' : 'var(--border-primary)'}`,
            borderRadius: 6, cursor: 'pointer',
            background: isFocused ? 'var(--accent-blue)' : 'transparent',
            color: isFocused ? '#fff' : 'var(--accent-blue)',
            fontWeight: 500, flexShrink: 0,
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

const PAGE_SIZE = 20

function sortProperties(props: PropertyResponse[], sortBy: string): PropertyResponse[] {
  return [...props].sort((a, b) => {
    if (sortBy === 'assessed_value') return (b.assessed_value ?? 0) - (a.assessed_value ?? 0)
    if (sortBy === 'address') return (a.address ?? '').localeCompare(b.address ?? '')
    return (a.year_built ?? 9999) - (b.year_built ?? 9999) // oldest first
  })
}

/** Extract street name from an address like "3380 SCOTT DR SW" → "SCOTT DR SW" */
function extractStreet(address: string | null | undefined): string {
  if (!address) return 'Unknown'
  const trimmed = address.trim()
  // Strip leading house number(s) and whitespace
  const match = trimmed.match(/^\d+[-\s]*\d*\s+(.+)/)
  return match ? match[1].replace(/\s+/g, ' ').trim() : trimmed
}

type StreetGroup = { street: string; properties: PropertyResponse[]; avgAge: number | null }

function groupByStreet(props: PropertyResponse[]): StreetGroup[] {
  const map = new Map<string, PropertyResponse[]>()
  for (const p of props) {
    const street = extractStreet(p.address)
    const list = map.get(street)
    if (list) list.push(p)
    else map.set(street, [p])
  }
  const groups: StreetGroup[] = []
  for (const [street, properties] of map) {
    const ages = properties.map(p => p.estimated_roof_age).filter((a): a is number => a != null)
    const avgAge = ages.length > 0 ? ages.reduce((s, a) => s + a, 0) / ages.length : null
    groups.push({ street, properties, avgAge })
  }
  // Sort groups A-Z by street name
  groups.sort((a, b) => a.street.localeCompare(b.street))
  return groups
}

function PropertyList({ zoneId, tractGeoid }: { zoneId: string; tractGeoid: string }) {
  const [sortBy, setSortBy] = useState('year_built')
  const [search, setSearch] = useState('')
  const [groupByStreetOn, setGroupByStreetOn] = useState(true)
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [expandedStreets, setExpandedStreets] = useState<Set<string>>(new Set())
  const { data, isLoading, error } = useTractProperties(zoneId, tractGeoid)
  const { data: pinsData } = useLeadPins()

  const pinByPropertyId = useMemo(() => {
    const map = new Map<string, LeadPinResponse>()
    if (pinsData?.pins) {
      for (const pin of pinsData.pins) {
        if (pin.property_id) map.set(pin.property_id, pin)
      }
    }
    return map
  }, [pinsData])

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
  if (!data || data.properties.length === 0) return <p style={{ color: 'var(--text-tertiary)', fontSize: 12, padding: '4px 0' }}>No properties found</p>

  const isNSI = data.source_county === 'NSI'

  // Data-driven: do enough properties have addresses to enable address features?
  const addressCount = data.properties.filter(
    p => p.address && /^\d/.test(p.address.trim())
  ).length
  const hasAddresses = addressCount > data.properties.length * 0.3

  // Filter out entries without a house number (e.g. vacant lots, utility parcels)
  // When no addresses available (first NSI load), show all properties unfiltered
  const withAddress = hasAddresses
    ? data.properties.filter(p => p.address && /^\d/.test(p.address.trim()))
    : data.properties

  const query = search.toLowerCase().trim()
  const filtered = query
    ? withAddress.filter(p =>
        (p.address ?? '').toLowerCase().includes(query) ||
        (p.owner_name ?? '').toLowerCase().includes(query)
      )
    : withAddress
  const sorted = sortProperties(filtered, sortBy)

  const toggleStreet = (street: string) => {
    setExpandedStreets(prev => {
      const next = new Set(prev)
      if (next.has(street)) next.delete(street)
      else next.add(street)
      return next
    })
  }

  // Flat view
  const visible = sorted.slice(0, visibleCount)
  const hasMore = visibleCount < sorted.length

  // Street-grouped view (only when addresses are available)
  const useStreetView = groupByStreetOn && hasAddresses
  const streetGroups = useStreetView ? groupByStreet(sorted) : []

  return (
    <div style={{ padding: '4px 0' }}>
      {/* Search */}
      <input
        type="text"
        placeholder={hasAddresses ? "Search address or owner..." : "Search by property type..."}
        value={search}
        onChange={e => { setSearch(e.target.value); setVisibleCount(PAGE_SIZE) }}
        style={{
          width: '100%', padding: '6px 8px', fontSize: 12, borderRadius: 6,
          border: '1px solid var(--border-primary)', background: 'var(--bg-secondary)',
          color: 'var(--text-primary)', marginBottom: 6, boxSizing: 'border-box',
          outline: 'none',
        }}
      />

      {/* Header: count + sort + group toggle */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6, flexWrap: 'wrap', gap: 4 }}>
        <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
          {query ? `${filtered.length} of ${withAddress.length}` : withAddress.length} properties · {isNSI ? 'Federal (NSI) data' : `${data.source_county} County`}
        </span>
        <div style={{ display: 'flex', gap: 4 }}>
          {hasAddresses && (
            <button
              onClick={() => setGroupByStreetOn(!groupByStreetOn)}
              style={{
                fontSize: 10, padding: '2px 6px', borderRadius: 4, cursor: 'pointer',
                border: `1px solid ${groupByStreetOn ? 'var(--accent-blue)' : 'var(--border-primary)'}`,
                background: groupByStreetOn ? 'var(--accent-blue)' : 'transparent',
                color: groupByStreetOn ? '#fff' : 'var(--text-secondary)',
              }}
            >
              Street
            </button>
          )}
          {(hasAddresses ? ['year_built', 'assessed_value', 'address'] as const : ['year_built', 'assessed_value'] as const).map(s => (
            <button
              key={s}
              onClick={() => { setSortBy(s); setVisibleCount(PAGE_SIZE) }}
              style={{
                fontSize: 10, padding: '2px 6px', borderRadius: 4, cursor: 'pointer',
                border: `1px solid ${!useStreetView && sortBy === s ? 'var(--accent-blue)' : 'var(--border-primary)'}`,
                background: !useStreetView && sortBy === s ? 'var(--accent-blue)' : 'transparent',
                color: !useStreetView && sortBy === s ? '#fff' : 'var(--text-secondary)',
              }}
            >
              {s === 'year_built' ? 'Age' : s === 'assessed_value' ? 'Value' : 'A-Z'}
            </button>
          ))}
        </div>
      </div>

      {useStreetView ? (
        /* ===== Street-grouped view ===== */
        <>
          {/* Column headers */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '4px 8px', marginBottom: 4,
            fontSize: 10, fontWeight: 600, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: 0.3,
          }}>
            <span style={{ width: 10 }} />
            <span style={{ flex: 1 }}>Street</span>
            <span style={{ minWidth: 40, textAlign: 'center' }}>Count</span>
            <span style={{ minWidth: 56, textAlign: 'center' }}>Avg Age</span>
          </div>
          {streetGroups.map(group => {
            const isExpanded = expandedStreets.has(group.street)
            const ageBadge = roofAgeBadge(group.avgAge != null ? Math.round(group.avgAge) : null)
            return (
              <div key={group.street} style={{ marginBottom: 4 }}>
                <button
                  onClick={() => toggleStreet(group.street)}
                  style={{
                    display: 'flex', alignItems: 'center', width: '100%', gap: 6,
                    padding: '6px 8px', border: '1px solid var(--border-primary)',
                    borderRadius: 6, cursor: 'pointer',
                    background: isExpanded ? 'var(--bg-tertiary)' : 'var(--bg-secondary)',
                    textAlign: 'left',
                  }}
                >
                  <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                    {isExpanded ? '▾' : '▸'}
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', flex: 1 }}>
                    {group.street}
                  </span>
                  <span style={{ fontSize: 10, color: 'var(--text-tertiary)', minWidth: 40, textAlign: 'center' }}>
                    {group.properties.length}
                  </span>
                  <span style={{
                    fontSize: 10, fontWeight: 600, padding: '1px 5px', borderRadius: 4,
                    minWidth: 56, textAlign: 'center',
                    background: ageBadge.bg, color: ageBadge.fg,
                  }}>
                    {ageBadge.label}
                  </span>
                </button>
                {isExpanded && (
                  <div style={{ paddingLeft: 8, paddingTop: 4 }}>
                    {group.properties.map(prop => <PropertyCard key={prop.id} property={prop} zoneId={zoneId} pin={pinByPropertyId.get(prop.id) ?? null} />)}
                  </div>
                )}
              </div>
            )
          })}
          <p style={{ fontSize: 11, color: 'var(--text-tertiary)', textAlign: 'center', padding: 4 }}>
            {streetGroups.length} streets · {sorted.length} properties
          </p>
        </>
      ) : (
        /* ===== Flat view ===== */
        <>
          {visible.map(prop => <PropertyCard key={prop.id} property={prop} zoneId={zoneId} pin={pinByPropertyId.get(prop.id) ?? null} />)}
          {hasMore ? (
            <button
              onClick={() => setVisibleCount(v => v + PAGE_SIZE)}
              style={{
                display: 'block', width: '100%', padding: '6px 0', marginTop: 4,
                fontSize: 11, fontWeight: 500, color: 'var(--accent-blue)',
                background: 'none', border: '1px solid var(--border-primary)',
                borderRadius: 6, cursor: 'pointer', textAlign: 'center',
              }}
            >
              Show more ({sorted.length - visibleCount} remaining)
            </button>
          ) : sorted.length > PAGE_SIZE ? (
            <p style={{ fontSize: 11, color: 'var(--text-tertiary)', textAlign: 'center', padding: 4 }}>
              All {sorted.length} properties shown
            </p>
          ) : null}
        </>
      )}
    </div>
  )
}

function PropertyCard({ property: p, zoneId, pin }: { property: PropertyResponse; zoneId: string; pin: LeadPinResponse | null }) {
  const badge = roofAgeBadge(p.estimated_roof_age)
  const setPendingPinLocation = useAppStore((s) => s.setPendingPinLocation)
  const deletePin = useDeleteLeadPin()
  const updatePin = useUpdateLeadPin()
  const [editing, setEditing] = useState(false)
  const hasCoords = p.latitude != null && p.longitude != null
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
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 16px' }}>
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

      {/* Row 5: Pin status + action */}
      {hasCoords && (
        pin ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 6 }}>
            <button
              onClick={() => setEditing(true)}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}
              title="Click to update status"
            >
              <DispositionBadge disposition={pin.disposition} />
            </button>
            <button
              onClick={() => deletePin.mutate(pin.id)}
              disabled={deletePin.isPending}
              style={{
                display: 'flex', alignItems: 'center', gap: 4,
                padding: '3px 8px', borderRadius: 5,
                border: '1px solid #ef4444', background: '#ef444410',
                cursor: deletePin.isPending ? 'wait' : 'pointer',
                fontSize: 10, fontWeight: 600, color: '#ef4444',
                opacity: deletePin.isPending ? 0.5 : 1,
              }}
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
              Unpin
            </button>
          </div>
        ) : (
          <button
            onClick={() => setPendingPinLocation({
              lat: p.latitude!, lon: p.longitude!,
              address: p.address ?? undefined,
              property_id: p.id,
              lead_zone_id: zoneId,
            })}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              marginTop: 6, padding: '4px 10px',
              borderRadius: 6, border: '1px solid #8b5cf6',
              background: '#8b5cf610', cursor: 'pointer',
              fontSize: 11, fontWeight: 600, color: '#8b5cf6',
            }}
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/>
              <circle cx="12" cy="10" r="3"/>
            </svg>
            Pin Lead
          </button>
        )
      )}

      {/* Update disposition modal */}
      {editing && pin && (
        <DispositionPicker
          title="Update Status"
          initialDisposition={pin.disposition as LeadPinDisposition}
          initialNotes={pin.notes ?? ''}
          onConfirm={(disposition, notes) => {
            updatePin.mutate(
              { pinId: pin.id, data: { disposition, notes: notes || undefined } },
              { onSuccess: () => setEditing(false) },
            )
          }}
          onCancel={() => setEditing(false)}
          isLoading={updatePin.isPending}
        />
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
