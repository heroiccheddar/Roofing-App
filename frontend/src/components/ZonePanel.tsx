import { useMemo, useState, useRef, useEffect } from 'react'
import useAppStore from '../stores/appStore'
import { useZoneList, useZoneDetail } from '../hooks/useZones'
import type { ZoneResponse } from '../types/api'
import FeedbackForm from './FeedbackForm'
import { haversineKm, formatDistance } from '../utils/distance'

function ZonePanel() {
  const selectedZoneId = useAppStore((s) => s.selectedZoneId)
  const setSelectedZoneId = useAppStore((s) => s.setSelectedZoneId)
  const minScore = useAppStore((s) => s.filters.minScore)
  const maxDistanceKm = useAppStore((s) => s.filters.maxDistanceKm)
  const leadType = useAppStore((s) => s.filters.leadType)
  const setFilters = useAppStore((s) => s.setFilters)
  const homeLat = useAppStore((s) => s.homeLat)
  const homeLon = useAppStore((s) => s.homeLon)
  const { data: zoneList, isLoading: listLoading } = useZoneList()
  const { data: detail } = useZoneDetail(selectedZoneId)

  // Compute distance for each zone + filter by maxDistance
  const zonesWithDistance = useMemo(() => {
    if (!zoneList?.zones) return []
    return zoneList.zones
      .map((zone) => {
        const distKm = (homeLat != null && homeLon != null)
          ? haversineKm(homeLat, homeLon, zone.centroid_lat, zone.centroid_lon)
          : null
        return { zone, distKm }
      })
      .filter(({ distKm }) => distKm === null || distKm <= maxDistanceKm)
      .sort((a, b) => (a.distKm ?? 0) - (b.distKm ?? 0))
  }, [zoneList, homeLat, homeLon, maxDistanceKm])

  // Distance for the detail view
  const detailDistance = useMemo(() => {
    if (!detail || homeLat == null || homeLon == null) return null
    return haversineKm(homeLat, homeLon, detail.centroid_lat, detail.centroid_lon)
  }, [detail, homeLat, homeLon])

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
            background: scoreColor(detail.composite_score).bg,
            color: scoreColor(detail.composite_score).fg,
          }}>
            {detail.score_band.toUpperCase()}
          </span>
          <span style={styles.scoreValue}>{detail.decay_adjusted_score.toFixed(1)}</span>
          {detailDistance !== null && (
            <span style={styles.distancePill}>{formatDistance(detailDistance)}</span>
          )}
        </div>
        <div style={styles.statGrid}>
          {detail.avg_roof_age_years != null && (
            <Stat label="Avg Home Age" value={`${detail.avg_roof_age_years.toFixed(0)} yrs`}
              info="Average age of homes in the zone. Older roofs are more likely to need replacement." />
          )}
          <Stat label="Lead Quality" value={detail.lead_quality.toFixed(1)}
            info="Composite score (0-100) based on demographics like income, home value, and ownership rate. Higher means better-quality leads." />
          <Stat label="Density Bonus" value={detail.density_bonus.toFixed(1)}
            info="Bonus for zones with high housing density. More homes in a small area means more efficient canvassing." />
          {(detail.lead_type === 'storm' || detail.event_count > 0) && (
            <>
              <Stat label="Damage Prob" value={detail.damage_prob.toFixed(1)}
                info="Estimated probability of roof damage (0-100) based on hail size, wind speed, and historical risk factors." />
              <Stat label="Events" value={String(detail.event_count)}
                info="Number of storm events (hail, wind, tornado) detected in this zone. More events increase confidence in damage." />
              <Stat label="Max Hail" value={detail.max_hail_diameter ? `${detail.max_hail_diameter}"` : 'N/A'}
                info="Largest hailstone diameter observed. 1&quot;+ hail can damage shingles; 2&quot;+ often causes significant roof damage." />
              <Stat label="Max Wind" value={detail.max_wind_speed ? `${detail.max_wind_speed} mph` : 'N/A'}
                info="Peak wind speed recorded. Winds above 60 mph can lift shingles and cause structural damage." />
              <Stat label="Hours Ago" value={detail.hours_since_storm.toFixed(1)}
                info="Time since the most recent storm event. Fresher leads convert better — scores decay over time." />
            </>
          )}
          <Stat label="Conversion" value={detail.predicted_conversion_rate ? `${(detail.predicted_conversion_rate * 100).toFixed(0)}%` : 'N/A'}
            info="Model-predicted likelihood that a lead in this zone converts to a signed roofing job." />
        </div>
        {/* Area Intelligence */}
        {(detail.avg_median_income != null || detail.avg_single_family_pct != null ||
          detail.total_building_count != null || detail.svi_overall != null) && (
          <>
            <h3 style={{ marginTop: 16, marginBottom: 8, fontSize: 14, color: '#475569' }}>
              Area Intelligence
            </h3>
            <div style={styles.statGrid}>
              {detail.avg_median_income != null && (
                <Stat label="Median Income" value={`$${(detail.avg_median_income / 1000).toFixed(0)}k`}
                  info="Higher income areas have homeowners more likely to afford and prioritize roof repairs." />
              )}
              {detail.avg_single_family_pct != null && (
                <Stat label="Single Family" value={`${detail.avg_single_family_pct.toFixed(0)}%`}
                  info="Percentage of single-family homes. Higher % means more residential roofing opportunities." />
              )}
              {detail.avg_vacancy_rate != null && (
                <Stat label="Vacancy Rate" value={`${detail.avg_vacancy_rate.toFixed(1)}%`}
                  info="Lower vacancy means more occupied homes with owners who maintain their property." />
              )}
              {detail.avg_pct_built_before_1980 != null && (
                <Stat label="Pre-1980 Homes" value={`${detail.avg_pct_built_before_1980.toFixed(0)}%`}
                  info="Older homes are more likely to need roof replacement due to material degradation." />
              )}
              {detail.tree_canopy_mean_pct != null && (
                <Stat label="Tree Canopy" value={`${detail.tree_canopy_mean_pct.toFixed(0)}%`}
                  info="Dense tree cover increases storm damage risk from falling branches and debris." />
              )}
              {detail.dominant_decade != null && (
                <Stat label="Dominant Era" value={detail.dominant_decade}
                  info="The most common decade homes were built. Clustered age means many roofs nearing replacement at once." />
              )}
              {detail.total_building_count != null && (
                <Stat label="Buildings" value={detail.total_building_count.toLocaleString()}
                  info="Total building footprints in the zone. More buildings means a larger addressable market." />
              )}
              {detail.avg_building_area_sqm != null && (
                <Stat label="Avg Bldg Size" value={`${detail.avg_building_area_sqm.toFixed(0)} m\u00B2`}
                  info="Larger buildings typically mean bigger roofing jobs and higher revenue per lead." />
              )}
              {detail.pct_cost_burdened != null && (
                <Stat label="Cost Burdened" value={`${detail.pct_cost_burdened.toFixed(0)}%`}
                  info="% of homeowners spending 30%+ of income on housing. Lower burden means more discretionary budget for roof work." />
              )}
              {detail.hpi_5yr_change != null && (
                <Stat label="Home Price Trend" value={`${detail.hpi_5yr_change > 0 ? '+' : ''}${detail.hpi_5yr_change.toFixed(1)}%`}
                  info="5-year home price change. Rising values mean homeowners are more willing to invest in repairs to protect equity." />
              )}
              {detail.redfin_median_sale_price != null && (
                <Stat label="Median Sale Price" value={
                  detail.redfin_median_sale_price >= 1000000
                    ? `$${(detail.redfin_median_sale_price / 1000000).toFixed(2)}M`
                    : `$${(detail.redfin_median_sale_price / 1000).toFixed(0)}k`
                }
                  info="Redfin median home sale price. Higher values mean larger roofing contracts and homeowners who invest in quality repairs." />
              )}
              {detail.redfin_median_dom != null && (
                <Stat label="Days on Market" value={`${detail.redfin_median_dom.toFixed(0)} days`}
                  info="Redfin median days on market. Low DOM means a hot market — homeowners are investing to increase resale value, including new roofs." />
              )}
              {detail.redfin_price_drop_pct != null && (
                <Stat label="Price Drops" value={`${detail.redfin_price_drop_pct.toFixed(1)}%`}
                  info="Percentage of listings with price reductions. Low price drops indicate a strong seller's market where homes hold value." />
              )}
              {detail.ruca_category != null && (
                <Stat label="Area Type" value={
                  detail.ruca_category === 'urban' ? 'Urban' :
                  detail.ruca_category === 'large_rural' ? 'Large Rural' :
                  detail.ruca_category === 'small_town' ? 'Small Town' :
                  detail.ruca_category === 'isolated_rural' ? 'Isolated Rural' :
                  detail.ruca_category
                }
                  info="USDA urban-rural classification. Urban areas have more competition but higher density. Rural areas may have less competition and longer drive times." />
              )}
              {detail.bps_single_family_permits != null && (
                <Stat label="New Construction" value={detail.bps_single_family_permits.toLocaleString()}
                  info="Annual single-family building permits in the county. High permits indicate growth areas with new roofs — less immediate need but future warranty/maintenance leads." />
              )}
              {detail.bps_total_value != null && detail.bps_total_value > 0 && (
                <Stat label="Permit Value" value={
                  detail.bps_total_value >= 1000000000
                    ? `$${(detail.bps_total_value / 1000000000).toFixed(1)}B`
                    : `$${(detail.bps_total_value / 1000000).toFixed(0)}M`
                }
                  info="Total annual construction value in the county. Higher values indicate affluent, active building markets — wealthier homeowners who invest in quality roofing." />
              )}
              {detail.ej_lead_paint != null && (
                <Stat label="Lead Paint Risk" value={`${detail.ej_lead_paint.toFixed(0)}%`}
                  info="EPA EJSCREEN: % of housing built before 1960, a proxy for lead paint presence. Older homes with lead paint often have aging roofs needing replacement." />
              )}
              {detail.ej_percentile != null && (
                <div style={{ padding: 8 }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                    EJ Burden
                    <InfoTip text="EPA Environmental Justice index percentile (0-100). Higher scores indicate areas with more environmental burden, often correlating with deferred maintenance and aging infrastructure." />
                  </div>
                  <ExposureBar score={detail.ej_percentile} />
                </div>
              )}
              {detail.flood_risk_category != null && (
                <Stat label="Flood Risk" value={
                  detail.flood_risk_category.charAt(0).toUpperCase() + detail.flood_risk_category.slice(1)
                }
                  info={`FEMA flood zone classification. ${detail.flood_insurance_required ? 'Flood insurance required — ' : ''}Higher flood risk means more weather-related property claims and homeowner awareness of damage risks.`} />
              )}
              {detail.svi_overall != null && (
                <div style={{ padding: 8 }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                    Social Vulnerability
                    <InfoTip text="CDC Social Vulnerability Index. Higher scores indicate communities more vulnerable to disasters, often correlating with greater storm damage impact." />
                  </div>
                  <ExposureBar score={detail.svi_overall * 100} />
                </div>
              )}
            </div>
          </>
        )}
        {/* Storm History */}
        {(detail.hail_exposure_score != null || detail.fema_disaster_score != null) && (
          <>
            <h3 style={{ marginTop: 16, marginBottom: 8, fontSize: 14, color: '#475569' }}>
              Storm History
            </h3>
            <div style={styles.statGrid}>
              {detail.hail_events_3yr != null && (
                <Stat label="Hail Events (3yr)" value={String(detail.hail_events_3yr)}
                  info="Radar-confirmed hail observations in the past 3 years. Repeated hail exposure weakens roofing materials over time." />
              )}
              {detail.hail_exposure_score != null && (
                <div style={{ padding: 8 }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                    Hail Exposure
                    <InfoTip text="Composite score (0-100) of historical hail severity and frequency. Higher scores indicate areas with chronic hail damage risk." />
                  </div>
                  <ExposureBar score={detail.hail_exposure_score} />
                </div>
              )}
              {detail.fema_disaster_count != null && (
                <Stat label="FEMA Disasters" value={String(detail.fema_disaster_count)}
                  info="Number of FEMA disaster declarations in the area. More declarations mean a proven track record of severe weather damage." />
              )}
              {detail.fema_disaster_score != null && (
                <div style={{ padding: 8 }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                    FEMA Score
                    <InfoTip text="Recency-weighted FEMA disaster score (0-100). Recent declarations score higher, reflecting current damage potential." />
                  </div>
                  <ExposureBar score={detail.fema_disaster_score} />
                </div>
              )}
              {detail.tree_canopy_risk_score != null && (
                <div style={{ padding: 8 }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                    Tree Canopy Risk
                    <InfoTip text="Risk score (0-100) from tree canopy density. Heavy tree cover amplifies storm damage from falling limbs and debris impact on roofs." />
                  </div>
                  <ExposureBar score={detail.tree_canopy_risk_score} />
                </div>
              )}
              {detail.age_clustering_score != null && (
                <div style={{ padding: 8 }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                    Age Clustering
                    <InfoTip text="How concentrated home ages are (0-100). High clustering means many homes built in the same era, so roofs age out together — great for batch canvassing." />
                  </div>
                  <ExposureBar score={detail.age_clustering_score} />
                </div>
              )}
              {detail.verified_damage_5yr_usd != null && (
                <Stat
                  label="Verified Damage (5yr)"
                  value={detail.verified_damage_5yr_usd >= 1000000
                    ? `$${(detail.verified_damage_5yr_usd / 1000000).toFixed(1)}M`
                    : `$${(detail.verified_damage_5yr_usd / 1000).toFixed(0)}K`}
                  info="NWS-verified property damage in the past 5 years. Ground-truth signal that severe weather causes real dollar losses here."
                />
              )}
              {detail.climate_weathering_score != null && (
                <div style={{ padding: 8 }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                    Climate Weathering
                    <InfoTip text="Index (0-100) of freeze-thaw cycles, UV exposure, rain, and wind. High scores mean the climate itself accelerates roof degradation." />
                  </div>
                  <ExposureBar score={detail.climate_weathering_score} />
                </div>
              )}
            </div>
          </>
        )}
        {/* FEMA Risk Index */}
        {(detail.nri_hail_risk || detail.nri_wind_risk || detail.nri_tornado_risk) && (
          <>
            <h3 style={{ marginTop: 16, marginBottom: 8, fontSize: 14, color: '#475569', display: 'flex', alignItems: 'center' }}>
              FEMA Risk Index
              <InfoTip text="FEMA National Risk Index ratings for natural hazards. Higher risk areas have a greater historical probability of severe weather events." />
            </h3>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {detail.nri_hail_risk && <RiskBadge label="Hail" rating={detail.nri_hail_risk}
                info="FEMA's assessment of hail risk frequency and severity for this area." />}
              {detail.nri_wind_risk && <RiskBadge label="Wind" rating={detail.nri_wind_risk}
                info="FEMA's assessment of straight-line wind risk for this area." />}
              {detail.nri_tornado_risk && <RiskBadge label="Tornado" rating={detail.nri_tornado_risk}
                info="FEMA's assessment of tornado risk for this area. Even 'Relatively Low' areas can have significant events." />}
            </div>
          </>
        )}
        {(detail.lead_type === 'storm' || detail.event_count > 0) && detail.events.length > 0 && (
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
        <div style={{ marginTop: 16 }}>
          <FeedbackForm zoneId={selectedZoneId} />
        </div>
      </div>
    )
  }

  // Zone list view
  return (
    <div style={styles.panel}>
      <h2 style={styles.heading}>Lead Zones</h2>
      <div style={styles.filterRow}>
        <label style={{ fontSize: 13, color: '#64748b' }}>Lead Type</label>
        <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
          {(['all', 'storm', 'roof_age'] as const).map((type) => (
            <button
              key={type}
              onClick={() => setFilters({ leadType: type })}
              style={{
                flex: 1,
                padding: '6px 0',
                border: '1px solid #e2e8f0',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: leadType === type ? 600 : 400,
                background: leadType === type ? '#2563eb' : '#fff',
                color: leadType === type ? '#fff' : '#64748b',
                cursor: 'pointer',
              }}
            >
              {type === 'all' ? 'All' : type === 'storm' ? 'Storm' : 'Home Age'}
            </button>
          ))}
        </div>
      </div>
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
      <div style={styles.filterRow}>
        <label style={{ fontSize: 13, color: '#64748b' }}>
          Max Distance: {maxDistanceKm >= 200 ? 'Any' : `${maxDistanceKm} km (${(maxDistanceKm * 0.621371).toFixed(0)} mi)`}
        </label>
        <input
          type="range"
          min={5} max={200} step={5}
          value={maxDistanceKm}
          onChange={(e) => setFilters({ maxDistanceKm: Number(e.target.value) })}
          style={{ width: '100%' }}
        />
      </div>
      {listLoading && <p style={{ color: '#64748b' }}>Loading zones...</p>}
      {zonesWithDistance.map(({ zone, distKm }) => (
        <div
          key={zone.id}
          onClick={() => setSelectedZoneId(zone.id)}
          style={styles.zoneCard}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{
              ...styles.scoreBadge,
              background: scoreColor(zone.composite_score).bg,
              color: scoreColor(zone.composite_score).fg,
            }}>
              {zone.score_band.toUpperCase()} {zone.composite_score.toFixed(0)}
            </span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {distKm !== null && (
                <span style={styles.distanceLabel}>{formatDistance(distKm)}</span>
              )}
              {(zone.lead_type === 'roof_age' || zone.event_count === 0) ? (
                <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 6px', borderRadius: 4, background: '#dcfce7', color: '#166534' }}>
                  Home Age
                </span>
              ) : (
                <span style={{ fontSize: 12, color: '#94a3b8' }}>
                  {zone.event_count} event{zone.event_count !== 1 ? 's' : ''}
                </span>
              )}
            </div>
          </div>
          <div style={{ marginTop: 4, fontSize: 13, color: '#475569' }}>
            {(zone.lead_type === 'storm' || zone.event_count > 0) && (
              <>
                {zone.max_hail_diameter ? `${zone.max_hail_diameter}" hail` : ''}
                {zone.max_hail_diameter && zone.max_wind_speed ? ' · ' : ''}
                {zone.max_wind_speed ? `${zone.max_wind_speed} mph wind` : ''}
              </>
            )}
          </div>
        </div>
      ))}
      {!listLoading && zonesWithDistance.length === 0 && (
        <p style={{ color: '#94a3b8', textAlign: 'center', marginTop: 32 }}>
          No zones found matching filters
        </p>
      )}
    </div>
  )
}

// Helper components
function InfoTip({ text }: { text: string }) {
  const [show, setShow] = useState(false)
  const tipRef = useRef<HTMLDivElement>(null)

  // Reposition if overflowing viewport
  useEffect(() => {
    if (show && tipRef.current) {
      const rect = tipRef.current.getBoundingClientRect()
      if (rect.right > window.innerWidth - 8) {
        tipRef.current.style.left = 'auto'
        tipRef.current.style.right = '0px'
      }
      if (rect.left < 8) {
        tipRef.current.style.left = '0px'
        tipRef.current.style.right = 'auto'
      }
    }
  }, [show])

  return (
    <span
      style={{ position: 'relative', display: 'inline-flex', marginLeft: 4, cursor: 'help' }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style={{ opacity: 0.45 }}>
        <circle cx="8" cy="8" r="7" stroke="#64748b" strokeWidth="1.5" />
        <text x="8" y="12" textAnchor="middle" fontSize="10" fontWeight="700" fill="#64748b">i</text>
      </svg>
      {show && (
        <div
          ref={tipRef}
          style={{
            position: 'absolute', bottom: 18, left: -8,
            background: '#1e293b', color: '#f1f5f9', fontSize: 11, lineHeight: '15px',
            padding: '6px 10px', borderRadius: 6, whiteSpace: 'normal',
            width: 200, zIndex: 100, boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            pointerEvents: 'none',
          }}
        >
          {text}
        </div>
      )}
    </span>
  )
}

function Stat({ label, value, info }: { label: string; value: string; info?: string }) {
  return (
    <div style={{ padding: 8 }}>
      <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
        {label}
        {info && <InfoTip text={info} />}
      </div>
      <div style={{ fontSize: 18, fontWeight: 600, color: '#0f172a' }}>{value}</div>
    </div>
  )
}

function ExposureBar({ score }: { score: number }) {
  const color = score > 60 ? '#dc2626' : score > 30 ? '#ca8a04' : '#16a34a'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
      <div style={{ flex: 1, height: 8, background: '#e2e8f0', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${Math.min(score, 100)}%`, height: '100%', background: color, borderRadius: 4 }} />
      </div>
      <span style={{ fontSize: 14, fontWeight: 600, color, minWidth: 32 }}>{score.toFixed(0)}</span>
    </div>
  )
}

function RiskBadge({ label, rating, info }: { label: string; rating: string; info?: string }) {
  const NRI_BG: Record<string, string> = {
    'Very High': '#fef2f2',
    'Relatively High': '#fff7ed',
    'Relatively Moderate': '#fefce8',
    'Relatively Low': '#f0fdf4',
    'Very Low': '#f0f9ff',
  }
  const NRI_COLOR: Record<string, string> = {
    'Very High': '#dc2626',
    'Relatively High': '#ea580c',
    'Relatively Moderate': '#ca8a04',
    'Relatively Low': '#16a34a',
    'Very Low': '#2563eb',
  }
  return (
    <span style={{
      fontSize: 12, padding: '4px 8px', borderRadius: 6,
      background: NRI_BG[rating] || '#f1f5f9',
      color: NRI_COLOR[rating] || '#64748b',
      fontWeight: 600, display: 'inline-flex', alignItems: 'center',
    }}>
      {label}: {rating}
      {info && <InfoTip text={info} />}
    </span>
  )
}

const BAND_BG: Record<string, string> = {
  hot: '#fef2f2', warm: '#fff7ed', cool: '#fefce8', skip: '#f1f5f9',
}
const BAND_COLOR: Record<string, string> = {
  hot: '#dc2626', warm: '#ea580c', cool: '#ca8a04', skip: '#64748b',
}

/** Return a hue-shifted background + text color based on composite score (0-100). */
function scoreColor(score: number): { bg: string; fg: string } {
  // Clamp to 0-100
  const s = Math.max(0, Math.min(100, score))
  // Map score to hue: 220 (blue) at 0 → 120 (green) at 50 → 30 (orange) at 75 → 0 (red) at 100
  let hue: number
  if (s <= 50) {
    hue = 220 - (s / 50) * 100  // 220 → 120
  } else if (s <= 75) {
    hue = 120 - ((s - 50) / 25) * 90  // 120 → 30
  } else {
    hue = 30 - ((s - 75) / 25) * 30  // 30 → 0
  }
  return {
    bg: `hsl(${hue}, 85%, 93%)`,
    fg: `hsl(${hue}, 70%, 35%)`,
  }
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
  distancePill: {
    fontSize: 13, color: '#2563eb', fontWeight: 500,
  },
  distanceLabel: {
    fontSize: 12, color: '#2563eb', fontWeight: 500,
  },
  statGrid: {
    display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4,
    background: '#f8fafc', borderRadius: 8, padding: 8,
  },
  filterRow: { marginBottom: 12 },
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
