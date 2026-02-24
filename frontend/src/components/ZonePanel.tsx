import { useMemo, useState, useRef, useEffect } from 'react'
import useAppStore from '../stores/appStore'
import { useZoneList, useZoneDetail } from '../hooks/useZones'
import FeedbackForm from './FeedbackForm'
import CanvassTracker from './CanvassTracker'
import { haversineKm, formatDistance } from '../utils/distance'
import { ZoneListSkeleton } from './SkeletonLoader'
import ErrorBoundary from './ErrorBoundary'

function ZonePanel({ isMobile = false }: { isMobile?: boolean }) {
  const selectedZoneId = useAppStore((s) => s.selectedZoneId)
  const setSelectedZoneId = useAppStore((s) => s.setSelectedZoneId)
  const minScore = useAppStore((s) => s.filters.minScore)
  const maxDistanceKm = useAppStore((s) => s.filters.maxDistanceKm)
  const leadType = useAppStore((s) => s.filters.leadType)
  const setFilters = useAppStore((s) => s.setFilters)
  const homeLat = useAppStore((s) => s.homeLat)
  const homeLon = useAppStore((s) => s.homeLon)
  const listViewMode = useAppStore((s) => s.listViewMode)
  const setListViewMode = useAppStore((s) => s.setListViewMode)
  const sortBy = useAppStore((s) => s.sortBy)
  const setSortBy = useAppStore((s) => s.setSortBy)
  const toggleZoneInRoute = useAppStore((s) => s.toggleZoneInRoute)
  const routeZoneIds = useAppStore((s) => s.routeZoneIds)
  const { data: zoneList, isLoading: listLoading, error: listError } = useZoneList()
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
  }, [zoneList, homeLat, homeLon, maxDistanceKm])

  // Sort zones based on selected sort mode
  const sortedZones = useMemo(() => {
    const list = [...zonesWithDistance]
    switch (sortBy) {
      case 'nearest':
        list.sort((a, b) => {
          if (a.distKm === null) return 1
          if (b.distKm === null) return -1
          return a.distKm - b.distKm
        })
        break
      case 'route':
        list.sort((a, b) => {
          const routeA = a.distKm !== null
            ? a.zone.composite_score / (1 + a.distKm * 0.1)
            : a.zone.composite_score * 0.1
          const routeB = b.distKm !== null
            ? b.zone.composite_score / (1 + b.distKm * 0.1)
            : b.zone.composite_score * 0.1
          return routeB - routeA
        })
        break
      case 'score':
      default:
        break
    }
    return list
  }, [zonesWithDistance, sortBy])

  // Distance for the detail view
  const detailDistance = useMemo(() => {
    if (!detail || homeLat == null || homeLon == null) return null
    return haversineKm(homeLat, homeLon, detail.centroid_lat, detail.centroid_lon)
  }, [detail, homeLat, homeLon])

  // Determine whether to show storm section in detail
  const showStormSection = detail
    ? (detail.has_active_storm === true || detail.lead_type === 'storm_boosted' || detail.event_count > 0)
    : false

  // If a zone is selected, show detail view
  if (selectedZoneId && detail) {
    return (
      <div style={{ ...styles.panel, height: '100%', overflowY: 'auto' }}>
        <button onClick={() => setSelectedZoneId(null)} style={styles.backBtn}>
          Back to list
        </button>
        <h2 style={styles.heading}>Zone Detail</h2>
        {detail.display_name && (
          <div style={{ fontSize: 14, color: 'var(--text-secondary)', fontWeight: 500, marginTop: -12, marginBottom: 12 }}>
            {detail.display_name}
          </div>
        )}

        {/* ===== 1. Score Overview ===== */}
        <div style={styles.sectionCard}>
          <h3 style={styles.sectionHeading}>Score Overview</h3>
          <div style={styles.scoreCard}>
            <span style={{
              ...styles.scoreBadge,
              background: scoreColor(detail.composite_score).bg,
              color: scoreColor(detail.composite_score).fg,
            }}>
              {detail.score_band.toUpperCase()}
            </span>
            <span style={styles.scoreValue}>{detail.decay_adjusted_score.toFixed(1)}</span>
            {showStormSection && detail.storm_boost != null && (
              <span style={{
                fontSize: 12, fontWeight: 600, padding: '3px 8px', borderRadius: 6,
                background: '#fff7ed', color: '#c2410c', border: '1px solid #fdba74',
              }}>
                Storm +{detail.storm_boost.toFixed(0)}
              </span>
            )}
            {detailDistance !== null && (
              <span style={styles.distancePill}>{formatDistance(detailDistance)}</span>
            )}
          </div>
          {detail.base_score != null && (
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>
              Base score: <strong>{detail.base_score.toFixed(1)}</strong>
            </div>
          )}
          {/* Why This Score */}
          {detail.score_factors && detail.score_factors.length > 0 && (
            <>
              <h3 style={{ marginTop: 12, marginBottom: 8, fontSize: 14, color: '#475569', display: 'flex', alignItems: 'center' }}>
                Why This Score
                <InfoTip text="Top factors contributing to this zone's composite score. Bars show each factor's percentile rank in the area; points show its weighted contribution to the final score." />
              </h3>
              <div style={{ background: 'var(--bg-secondary)', borderRadius: 8, padding: '10px 12px', marginBottom: 0 }}>
                {detail.score_factors.map((factor, i) => {
                  const maxContribution = detail.score_factors![0].contribution
                  const barPct = maxContribution > 0 ? (factor.contribution / maxContribution) * 100 : 0
                  const colors = scoreColor(factor.percentile)
                  return (
                    <div key={factor.name} style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '5px 0',
                      borderBottom: i < detail.score_factors!.length - 1 ? '1px solid #e2e8f0' : 'none',
                    }}>
                      <div style={{ width: isMobile ? 80 : 100, fontSize: 12, fontWeight: 500, color: '#334155', flexShrink: 0 }}>
                        {factor.label}
                      </div>
                      <div style={{ fontSize: 11, color: '#94a3b8', width: isMobile ? 40 : 50, textAlign: 'right', flexShrink: 0 }}>
                        {isMobile ? `${Math.round(factor.percentile)}%` : `${ordinal(factor.percentile)} pctile`}
                      </div>
                      <div style={{ flex: 1, height: 10, background: '#e2e8f0', borderRadius: 5, overflow: 'hidden' }}>
                        <div style={{
                          width: `${barPct}%`, height: '100%',
                          background: colors.fg, borderRadius: 5,
                          transition: 'width 0.3s ease',
                        }} />
                      </div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: colors.fg, minWidth: 44, textAlign: 'right' }}>
                        {factor.contribution.toFixed(1)} pts
                      </div>
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </div>

        {/* ===== 2. Roof Condition ===== */}
        <div style={styles.sectionCard}>
          <h3 style={{ ...styles.sectionHeading, display: 'flex', alignItems: 'center' }}>
            Roof Condition
            <InfoTip text="Likelihood that roofs in this area need replacement based on age, climate exposure, and construction era." />
          </h3>
          <SubScoreBar label="Roof Condition Score" value={detail.roof_condition} color="#e67e22" />
          <div style={{ ...styles.statGrid, gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr' }}>
            {detail.avg_roof_age_years != null && (
              <Stat label="Avg Home Age" value={`${detail.avg_roof_age_years.toFixed(0)} yrs`}
                info="Average age of homes in the zone. Older roofs are more likely to need replacement." />
            )}
            {detail.dominant_decade != null && (
              <Stat label="Dominant Era" value={detail.dominant_decade}
                info="The most common decade homes were built. Clustered age means many roofs nearing replacement at once." />
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
            {detail.avg_pct_built_before_1980 != null && (
              <Stat label="Pre-1980 Homes" value={`${detail.avg_pct_built_before_1980.toFixed(0)}%`}
                info="Older homes are more likely to need roof replacement due to material degradation." />
            )}
          </div>
        </div>

        {/* ===== 3. Market Quality ===== */}
        <div style={styles.sectionCard}>
          <h3 style={{ ...styles.sectionHeading, display: 'flex', alignItems: 'center' }}>
            Market Quality
            <InfoTip text="Homeowner willingness and ability to invest in roof replacement." />
          </h3>
          <SubScoreBar label="Market Quality Score" value={detail.market_quality} color="#27ae60" />
          <div style={{ ...styles.statGrid, gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr' }}>
            {detail.avg_median_income != null && (
              <Stat label="Median Income" value={`$${(detail.avg_median_income / 1000).toFixed(0)}k`}
                info="Higher income areas have homeowners more likely to afford and prioritize roof repairs." />
            )}
            {detail.avg_single_family_pct != null && (
              <Stat label="Owner Occupied" value={`${detail.avg_single_family_pct.toFixed(0)}%`}
                info="Percentage of owner-occupied single-family homes. Higher % means more residential roofing opportunities." />
            )}
            {detail.redfin_median_sale_price != null && (
              <Stat label="Median Sale Price" value={
                detail.redfin_median_sale_price >= 1000000
                  ? `$${(detail.redfin_median_sale_price / 1000000).toFixed(2)}M`
                  : `$${(detail.redfin_median_sale_price / 1000).toFixed(0)}k`
              }
                info="Redfin median home sale price. Higher values mean larger roofing contracts and homeowners who invest in quality repairs." />
            )}
            {detail.hpi_5yr_change != null && (
              <Stat label="Home Price Trend" value={`${detail.hpi_5yr_change > 0 ? '+' : ''}${detail.hpi_5yr_change.toFixed(1)}%`}
                info="5-year home price change. Rising values mean homeowners are more willing to invest in repairs to protect equity." />
            )}
          </div>
        </div>

        {/* ===== 4. Risk Exposure ===== */}
        <div style={styles.sectionCard}>
          <h3 style={{ ...styles.sectionHeading, display: 'flex', alignItems: 'center' }}>
            Risk Exposure
            <InfoTip text="Environmental and historical risk factors that increase roof damage likelihood." />
          </h3>
          <SubScoreBar label="Risk Exposure Score" value={detail.risk_exposure} color="#e74c3c" />
          <div style={{ ...styles.statGrid, gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr' }}>
            {detail.hail_exposure_score != null && (
              <div style={{ padding: 8 }}>
                <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                  Hail Exposure
                  <InfoTip text="Composite score (0-100) of historical hail severity and frequency. Higher scores indicate areas with chronic hail damage risk." />
                </div>
                <ExposureBar score={detail.hail_exposure_score} />
              </div>
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
                  <InfoTip text="Risk score (0-100) from tree canopy density. Heavy tree cover amplifies damage risk from falling limbs and debris impact on roofs." />
                </div>
                <ExposureBar score={detail.tree_canopy_risk_score} />
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
          </div>
          {/* FEMA Risk Index */}
          {(detail.nri_hail_risk || detail.nri_wind_risk || detail.nri_tornado_risk) && (
            <>
              <h4 style={{ margin: '12px 0 6px', fontSize: 13, color: '#475569', display: 'flex', alignItems: 'center' }}>
                FEMA Risk Index
                <InfoTip text="FEMA National Risk Index ratings for natural hazards. Higher risk areas have a greater historical probability of severe weather events." />
              </h4>
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
        </div>

        {/* ===== 5. Canvass Efficiency ===== */}
        <div style={styles.sectionCard}>
          <h3 style={{ ...styles.sectionHeading, display: 'flex', alignItems: 'center' }}>
            Canvass Efficiency
            <InfoTip text="How efficiently a canvassing team can cover this area." />
          </h3>
          <SubScoreBar label="Canvass Efficiency Score" value={detail.canvass_efficiency} color="#3498db" />
          <div style={{ ...styles.statGrid, gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr' }}>
            {detail.total_building_count != null && (
              <Stat label="Buildings" value={detail.total_building_count.toLocaleString()}
                info="Total building footprints in the zone. More buildings means a larger addressable market." />
            )}
            {detail.avg_building_area_sqm != null && (
              <Stat label="Avg Bldg Size" value={`${detail.avg_building_area_sqm.toFixed(0)} m\u00B2`}
                info="Larger buildings typically mean bigger roofing jobs and higher revenue per lead." />
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
            <Stat label="Conversion" value={detail.predicted_conversion_rate ? `${(detail.predicted_conversion_rate * 100).toFixed(0)}%` : 'N/A'}
              info="Model-predicted likelihood that a lead in this zone converts to a signed roofing job." />
          </div>
        </div>

        {/* ===== 6. Active Storm Data (conditional) ===== */}
        {showStormSection && (
          <div style={{ ...styles.sectionCard, borderLeft: '3px solid #f97316' }}>
            <h3 style={{ ...styles.sectionHeading, display: 'flex', alignItems: 'center', color: '#c2410c' }}>
              Active Storm Data
              <InfoTip text="Recent severe weather activity boosting this zone's score." />
            </h3>
            {detail.storm_boost != null && (
              <SubScoreBar label="Storm Boost" value={detail.storm_boost} color="#f97316" />
            )}
            <div style={{ ...styles.statGrid, gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr' }}>
              <Stat label="Damage Prob" value={detail.damage_prob.toFixed(1)}
                info="Roof condition assessment based on age, climate, and construction era, boosted by active storm signals." />
              <Stat label="Events" value={String(detail.event_count)}
                info="Active severe weather events in this zone." />
              <Stat label="Max Hail" value={detail.max_hail_diameter ? `${detail.max_hail_diameter}"` : 'N/A'}
                info="Largest hailstone diameter observed. 1&quot;+ hail can damage shingles; 2&quot;+ often causes significant roof damage." />
              <Stat label="Max Wind" value={detail.max_wind_speed ? `${detail.max_wind_speed} mph` : 'N/A'}
                info="Peak wind speed recorded. Winds above 60 mph can lift shingles and cause structural damage." />
              <Stat label="Hours Ago" value={detail.hours_since_storm.toFixed(1)}
                info="Time since the most recent storm event. Fresher leads convert better — scores decay over time." />
            </div>
            {detail.events.length > 0 && (
              <>
                <h4 style={{ margin: '12px 0 6px', fontSize: 13, color: '#475569' }}>Storm Events</h4>
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
        )}

        {/* ===== Additional area intelligence (supplementary stats) ===== */}
        {(detail.avg_vacancy_rate != null || detail.pct_cost_burdened != null ||
          detail.redfin_median_dom != null || detail.redfin_price_drop_pct != null ||
          detail.bps_single_family_permits != null || detail.bps_total_value != null ||
          detail.ej_lead_paint != null || detail.ej_percentile != null ||
          detail.svi_overall != null || detail.flood_risk_category != null ||
          detail.age_clustering_score != null || detail.hail_events_3yr != null ||
          detail.fema_disaster_count != null) && (
          <>
            <h3 style={{ marginTop: 16, marginBottom: 8, fontSize: 14, color: 'var(--text-secondary)' }}>
              Area Intelligence
            </h3>
            <div style={{ ...styles.statGrid, gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr' }}>
              {detail.avg_vacancy_rate != null && (
                <Stat label="Vacancy Rate" value={`${detail.avg_vacancy_rate.toFixed(1)}%`}
                  info="Lower vacancy means more occupied homes with owners who maintain their property." />
              )}
              {detail.pct_cost_burdened != null && (
                <Stat label="Cost Burdened" value={`${detail.pct_cost_burdened.toFixed(0)}%`}
                  info="% of homeowners spending 30%+ of income on housing. Lower burden means more discretionary budget for roof work." />
              )}
              {detail.redfin_median_dom != null && (
                <Stat label="Days on Market" value={`${detail.redfin_median_dom.toFixed(0)} days`}
                  info="Redfin median days on market. Low DOM means a hot market — homeowners are investing to increase resale value, including new roofs." />
              )}
              {detail.redfin_price_drop_pct != null && (
                <Stat label="Price Drops" value={`${detail.redfin_price_drop_pct.toFixed(1)}%`}
                  info="Percentage of listings with price reductions. Low price drops indicate a strong seller's market where homes hold value." />
              )}
              {detail.hail_events_3yr != null && (
                <Stat label="Hail Events (3yr)" value={String(detail.hail_events_3yr)}
                  info="Radar-confirmed hail observations in the past 3 years. Repeated hail exposure weakens roofing materials over time." />
              )}
              {detail.fema_disaster_count != null && (
                <Stat label="FEMA Disasters" value={String(detail.fema_disaster_count)}
                  info="Number of FEMA disaster declarations in the area. More declarations mean a proven track record of severe weather damage." />
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
                  info="Total annual construction value in the county. Higher values indicate affluent, active building markets." />
              )}
              {detail.ej_lead_paint != null && (
                <Stat label="Lead Paint Risk" value={`${detail.ej_lead_paint.toFixed(0)}%`}
                  info="EPA EJSCREEN: % of housing built before 1960, a proxy for lead paint presence. Older homes with lead paint often have aging roofs needing replacement." />
              )}
              {detail.age_clustering_score != null && (
                <div style={{ padding: 8 }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                    Age Clustering
                    <InfoTip text="How concentrated home ages are (0-100). High clustering means many homes built in the same era, so roofs age out together." />
                  </div>
                  <ExposureBar score={detail.age_clustering_score} />
                </div>
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
                  info={`FEMA flood zone classification. ${detail.flood_insurance_required ? 'Flood insurance required. ' : ''}Higher flood risk means more weather-related property claims and homeowner awareness of damage risks.`} />
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

        <div style={{ marginTop: 16 }}>
          <CanvassTracker zoneId={selectedZoneId} />
        </div>
        <div style={{ marginTop: 16 }}>
          <FeedbackForm zoneId={selectedZoneId} />
        </div>
      </div>
    )
  }

  // Zone list view
  return (
    <div style={{ ...styles.panel, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ ...styles.heading, margin: 0 }}>Lead Zones</h2>
        <div style={{ display: 'flex', gap: 2, background: 'var(--bg-tertiary)', borderRadius: 6, padding: 2 }}>
          {(['cards', 'table'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setListViewMode(mode)}
              style={{
                padding: '4px 10px', border: 'none', borderRadius: 4, fontSize: 12,
                fontWeight: listViewMode === mode ? 600 : 400,
                background: listViewMode === mode ? 'var(--card-bg)' : 'transparent',
                color: listViewMode === mode ? 'var(--text-primary)' : 'var(--text-tertiary)',
                cursor: 'pointer',
                boxShadow: listViewMode === mode ? '0 1px 2px rgba(0,0,0,0.08)' : 'none',
              }}
            >
              {mode === 'cards' ? 'Cards' : 'Table'}
            </button>
          ))}
        </div>
      </div>
      <div style={styles.filterRow}>
        <label style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Lead Type</label>
        <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
          {(['all', 'storm_boosted', 'standard'] as const).map((type) => (
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
                background: leadType === type ? 'var(--accent-blue)' : 'var(--card-bg)',
                color: leadType === type ? '#fff' : 'var(--text-secondary)',
                cursor: 'pointer',
              }}
            >
              {type === 'all' ? 'All' : type === 'storm_boosted' ? 'Storm Boosted' : 'Standard'}
            </button>
          ))}
        </div>
      </div>
      <div style={styles.filterRow}>
        <label style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Min Score: {minScore}</label>
        <input
          type="range"
          min={0} max={100}
          value={minScore}
          onChange={(e) => setFilters({ minScore: Number(e.target.value) })}
          style={{ width: '100%' }}
        />
      </div>
      <div style={styles.filterRow}>
        <label style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
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
      <div style={styles.filterRow}>
        <label style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Sort By</label>
        <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
          {([
            { key: 'score' as const, label: 'Top Score' },
            { key: 'nearest' as const, label: 'Nearest' },
            { key: 'route' as const, label: 'Best Route' },
          ]).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setSortBy(key)}
              style={{
                flex: 1,
                padding: '6px 0',
                border: '1px solid #e2e8f0',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: sortBy === key ? 600 : 400,
                background: sortBy === key ? 'var(--accent-blue)' : 'var(--card-bg)',
                color: sortBy === key ? '#fff' : 'var(--text-secondary)',
                cursor: 'pointer',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {listLoading && <ZoneListSkeleton count={5} />}
      {listError && <p style={{ color: '#dc2626', fontSize: 13 }}>Error: {(listError as Error).message}</p>}
      {!listLoading && sortedZones.length > 0 && (
        <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>
          {sortedZones.length} zones{sortBy === 'score' ? ' by score' : sortBy === 'nearest' ? ' by distance' : ' by route efficiency'}
        </div>
      )}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
      {listViewMode === 'table' ? (
        /* Table View */
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                <th style={styles.th}>Score</th>
                <th style={styles.th}>Location</th>
                <th style={styles.th}>Type</th>
                <th style={styles.th}>Dist</th>
              </tr>
            </thead>
            <tbody>
              {sortedZones.map(({ zone, distKm }, i) => (
                <tr
                  key={zone.id}
                  onClick={() => setSelectedZoneId(zone.id)}
                  style={{
                    cursor: 'pointer',
                    background: i % 2 === 0 ? 'var(--card-bg)' : 'var(--bg-secondary)',
                    borderBottom: '1px solid #f1f5f9',
                    height: 32,
                  }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = '#eff6ff' }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = i % 2 === 0 ? 'var(--card-bg)' : 'var(--bg-secondary)' }}
                >
                  <td style={styles.td}>
                    <span style={{
                      padding: '2px 6px', borderRadius: 4, fontWeight: 600, fontSize: 11,
                      background: scoreColor(zone.composite_score).bg,
                      color: scoreColor(zone.composite_score).fg,
                    }}>
                      {zone.composite_score.toFixed(0)}
                    </span>
                  </td>
                  <td style={{ ...styles.td, maxWidth: 110, overflow: 'hidden', textOverflow: 'ellipsis', color: '#475569' }}>
                    {zone.display_name || '-'}
                  </td>
                  <td style={styles.td}>
                    {(zone.has_active_storm || zone.lead_type === 'storm_boosted') ? (
                      <span style={{ fontSize: 10, fontWeight: 600, padding: '1px 4px', borderRadius: 3, background: '#fff7ed', color: '#c2410c' }}>Storm +</span>
                    ) : null}
                  </td>
                  <td style={{ ...styles.td, color: '#2563eb' }}>
                    {distKm !== null ? formatDistance(distKm) : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        /* Card View */
        sortedZones.map(({ zone, distKm }) => (
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
                {(zone.has_active_storm || zone.lead_type === 'storm_boosted') && (
                  <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 6px', borderRadius: 4, background: '#fff7ed', color: '#c2410c', border: '1px solid #fdba74' }}>
                    Storm +
                  </span>
                )}
                <button
                  onClick={(e) => { e.stopPropagation(); toggleZoneInRoute(zone.id) }}
                  style={{
                    padding: '2px 6px', fontSize: 11, borderRadius: 4,
                    background: routeZoneIds.includes(zone.id) ? 'var(--accent-blue)' : 'var(--bg-tertiary)',
                    color: routeZoneIds.includes(zone.id) ? '#fff' : 'var(--text-secondary)',
                    border: 'none', cursor: 'pointer',
                  }}
                  title={routeZoneIds.includes(zone.id) ? 'Remove from route' : 'Add to route'}
                >
                  {routeZoneIds.includes(zone.id) ? '\u2713 Route' : '+ Route'}
                </button>
              </div>
            </div>
            {zone.display_name && (
              <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-secondary)', fontWeight: 500 }}>
                {zone.display_name}
              </div>
            )}
          </div>
        ))
      )}
      {!listLoading && sortedZones.length === 0 && (
        <p style={{ color: 'var(--text-tertiary)', textAlign: 'center', marginTop: 32 }}>
          No zones found matching filters
        </p>
      )}
      </div>
    </div>
  )
}

/** Format a number as an ordinal (1st, 2nd, 3rd, etc.) */
function ordinal(n: number): string {
  const r = Math.round(n)
  const s = ['th', 'st', 'nd', 'rd']
  const v = r % 100
  return r + (s[(v - 20) % 10] || s[v] || s[0])
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
            width: 200, maxWidth: 'calc(100vw - 32px)', zIndex: 100, boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
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

const SubScoreBar = ({ label, value, color }: { label: string; value?: number; color: string }) => {
  if (value == null) return null
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
        <span>{label}</span>
        <span style={{ fontWeight: 600 }}>{value.toFixed(0)}</span>
      </div>
      <div style={{ height: 6, background: '#e0e0e0', borderRadius: 3 }}>
        <div style={{ height: '100%', width: `${Math.min(value, 100)}%`, background: color, borderRadius: 3 }} />
      </div>
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


/** Return background + text color for a composite score (0-100).
 *
 * 21 color stops (every 5 points) with distinct color families.
 * Extra differentiation in the 80-100 range where lead quality matters most.
 *
 *   0-15  → grays / steel        (skip band)
 *  20-25  → blue / indigo        (cool low-end)
 *  30-45  → violet / purple      (cool band)
 *  50-65  → teal / emerald       (warm band)
 *  70-80  → lime / yellow / amber (hot low-end)
 *  85-100 → orange → red → crimson → magenta (hot high-end)
 */
function scoreColor(score: number): { bg: string; fg: string } {
  const s = Math.max(0, Math.min(100, score))

  // Color stops: [score, bgHex, fgHex]
  const stops: [number, string, string][] = [
    [  0, '#f1f5f9', '#64748b'],  // slate-100/500
    [  5, '#f0f1f3', '#5b6270'],  // gray-steel
    [ 10, '#e8edf4', '#475876'],  // blue-gray
    [ 15, '#e2e8f0', '#3b4f7a'],  // steel-blue
    [ 20, '#dbeafe', '#1e40af'],  // blue-100/800
    [ 25, '#e0e7ff', '#4338ca'],  // indigo-100/700
    [ 30, '#ede9fe', '#6d28d9'],  // violet-100/700
    [ 35, '#f3e8ff', '#7e22ce'],  // purple-100/700
    [ 40, '#fae8ff', '#a21caf'],  // fuchsia-100/700
    [ 45, '#fce7f3', '#9d174d'],  // pink-100/800
    [ 50, '#ccfbf1', '#0f766e'],  // teal-100/700
    [ 55, '#cffafe', '#0e7490'],  // cyan-100/700
    [ 60, '#d1fae5', '#047857'],  // emerald-100/700
    [ 65, '#dcfce7', '#15803d'],  // green-100/700
    [ 70, '#ecfccb', '#4d7c0f'],  // lime-100/700
    [ 75, '#fef9c3', '#a16207'],  // yellow-100/700
    [ 80, '#fef3c7', '#b45309'],  // amber-100/700
    [ 85, '#ffedd5', '#c2410c'],  // orange-100/700
    [ 90, '#fee2e2', '#dc2626'],  // red-100/600
    [ 95, '#ffe4e6', '#be123c'],  // rose-100/700
    [100, '#fae8ff', '#86198f'],  // fuchsia-100/800
  ]

  // Find the two stops we're between
  let lo = stops[0], hi = stops[stops.length - 1]
  for (let i = 0; i < stops.length - 1; i++) {
    if (s >= stops[i][0] && s <= stops[i + 1][0]) {
      lo = stops[i]
      hi = stops[i + 1]
      break
    }
  }

  const t = hi[0] === lo[0] ? 0 : (s - lo[0]) / (hi[0] - lo[0])
  return {
    bg: lerpColor(lo[1], hi[1], t),
    fg: lerpColor(lo[2], hi[2], t),
  }
}

/** Linearly interpolate between two hex colors. */
function lerpColor(a: string, b: string, t: number): string {
  const parse = (hex: string) => [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ]
  const ca = parse(a), cb = parse(b)
  const r = Math.round(ca[0] + (cb[0] - ca[0]) * t)
  const g = Math.round(ca[1] + (cb[1] - ca[1]) * t)
  const bl = Math.round(ca[2] + (cb[2] - ca[2]) * t)
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${bl.toString(16).padStart(2, '0')}`
}

const styles: Record<string, React.CSSProperties> = {
  panel: { padding: 16 },
  heading: { margin: '0 0 16px', fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' as any },
  backBtn: {
    background: 'none', border: 'none', color: 'var(--accent-blue)' as any, cursor: 'pointer',
    fontSize: 14, padding: 0, marginBottom: 8,
  },
  sectionCard: {
    background: 'var(--bg-secondary)' as any, borderRadius: 10, padding: 12, marginBottom: 12,
    border: '1px solid var(--border-primary)' as any,
  },
  sectionHeading: {
    margin: '0 0 10px', fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)' as any,
  },
  scoreCard: {
    display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8, flexWrap: 'wrap',
  },
  scoreBadge: {
    padding: '4px 10px', borderRadius: 6, fontSize: 13, fontWeight: 600,
  },
  scoreValue: { fontSize: 32, fontWeight: 700, color: 'var(--text-primary)' as any },
  distancePill: {
    fontSize: 13, color: 'var(--accent-blue)' as any, fontWeight: 500,
  },
  distanceLabel: {
    fontSize: 12, color: 'var(--accent-blue)' as any, fontWeight: 500,
  },
  statGrid: {
    display: 'grid', gap: 4,
    background: 'var(--card-bg)' as any, borderRadius: 8, padding: 4,
  },
  filterRow: { marginBottom: 12 },
  zoneCard: {
    padding: 12, marginBottom: 8, borderRadius: 8, border: '1px solid var(--border-primary)' as any,
    cursor: 'pointer', transition: 'background 0.15s',
    background: 'var(--card-bg)' as any,
  },
  eventCard: {
    display: 'flex', gap: 8, alignItems: 'center', padding: '6px 0',
    fontSize: 13, color: 'var(--text-secondary)' as any, borderBottom: '1px solid var(--border-primary)' as any,
  },
  eventSource: {
    fontSize: 11, fontWeight: 600, padding: '2px 6px', borderRadius: 4,
    background: 'var(--bg-tertiary)' as any, color: 'var(--text-secondary)' as any,
  },
  th: {
    textAlign: 'left' as const, padding: '6px 6px', fontSize: 11, fontWeight: 600,
    color: 'var(--text-secondary)' as any, textTransform: 'uppercase' as const, whiteSpace: 'nowrap' as const,
  },
  td: {
    padding: '4px 6px', fontSize: 12, color: 'var(--text-secondary)' as any, whiteSpace: 'nowrap' as const,
  },
}

function ZonePanelWithBoundary(props: { isMobile?: boolean }) {
  return (
    <ErrorBoundary>
      <ZonePanel {...props} />
    </ErrorBoundary>
  )
}

export default ZonePanelWithBoundary
