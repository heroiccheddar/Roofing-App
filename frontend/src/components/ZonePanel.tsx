import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import useAppStore from '../stores/appStore'
import { useZoneList, useZoneDetail } from '../hooks/useZones'
import FeedbackForm from './FeedbackForm'
import CanvassTracker from './CanvassTracker'
import LeadPinPanel from './LeadPinPanel'
import { haversineKm, formatDistance } from '../utils/distance'
import { scoreColor, ordinal } from '../utils/zoneFormatters'
import { InfoTip, Stat, ExposureBar, SubScoreBar, RiskBadge, FreshnessBadge } from './ZoneDetailHelpers'
import { ZoneCardSkeleton, ZoneListSkeleton } from './SkeletonLoader'
import ErrorBoundary from './ErrorBoundary'

function ZonePanel({ isMobile = false }: { isMobile?: boolean }) {
  const navigate = useNavigate()
  const selectedZoneId = useAppStore((s) => s.selectedZoneId)
  const setSelectedZoneId = useAppStore((s) => s.setSelectedZoneId)
  const selectedLeadPinId = useAppStore((s) => s.selectedLeadPinId)
  const minScore = useAppStore((s) => s.filters.minScore)
  const maxDistanceMiles = useAppStore((s) => s.filters.maxDistanceMiles)
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
  const { data: detail, isLoading: detailLoading } = useZoneDetail(selectedZoneId)

  // Compute distance for each zone + filter by maxDistance
  const maxDistanceKm = maxDistanceMiles * 1.60934
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

  // On mobile, when a lead pin is selected, show only the pin detail panel
  if (isMobile && selectedLeadPinId) {
    return (
      <div style={{ ...styles.panel, height: '100%', overflowY: 'auto' }}>
        <LeadPinPanel />
      </div>
    )
  }

  // Show skeleton while zone detail is loading
  if (selectedZoneId && !detail && detailLoading) {
    return (
      <div style={{ ...styles.panel, height: '100%', overflowY: 'auto' }}>
        <button onClick={() => setSelectedZoneId(null)} style={styles.backBtn}>
          Back to list
        </button>
        <ZoneCardSkeleton />
        <ZoneCardSkeleton />
        <ZoneCardSkeleton />
      </div>
    )
  }

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
            {detail.freshness && (
              <FreshnessBadge status={detail.freshness.status} label={detail.freshness.label} />
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

        <button
          onClick={() => navigate(`/zones/${selectedZoneId}`)}
          style={{
            display: 'block', width: '100%',
            padding: '10px 12px', marginBottom: 12,
            background: 'var(--accent-blue)', color: '#fff',
            border: 'none', borderRadius: 8, fontSize: 13, fontWeight: 600,
            cursor: 'pointer', textAlign: 'center',
          }}
        >
          View Full Details & Neighborhood Breakdown
        </button>

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

        {/* Lead Pins — visible in detail view too */}
        <div id="lead-pin-panel" style={{
          borderTop: '1px solid var(--border-primary)',
          marginTop: 12,
        }}>
          <LeadPinPanel />
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
          Max Distance: {maxDistanceMiles >= 200 ? 'Any' : `${maxDistanceMiles} mi`}
        </label>
        <input
          type="range"
          min={5} max={200} step={5}
          value={maxDistanceMiles}
          onChange={(e) => setFilters({ maxDistanceMiles: Number(e.target.value) })}
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
                <th style={styles.th}>Data</th>
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
                    {zone.freshness ? (
                      <FreshnessBadge status={zone.freshness.status} label={zone.freshness.label} compact />
                    ) : (zone.has_active_storm || zone.lead_type === 'storm_boosted') ? (
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
                {zone.freshness && (
                  <FreshnessBadge status={zone.freshness.status} label={zone.freshness.label} compact />
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

      {/* Lead Pins section — always visible in the list view */}
      <div id="lead-pin-panel" style={{
        borderTop: '1px solid var(--border-primary)',
        marginTop: 8,
        flexShrink: 0,
      }}>
        <LeadPinPanel />
      </div>
    </div>
  )
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
