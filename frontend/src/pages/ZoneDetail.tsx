/**
 * Full-screen Zone Detail page.
 *
 * Renders all zone data in collapsible sections with a prominent
 * Neighborhood Breakdown section showing census tracts ranked by canvass priority.
 *
 * Route: /zones/:id
 */
import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import useAppStore from '../stores/appStore'
import { useZoneDetail } from '../hooks/useZones'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { scoreColor, ordinal } from '../utils/zoneFormatters'
import { InfoTip, Stat, ExposureBar, SubScoreBar, RiskBadge } from '../components/ZoneDetailHelpers'
import TractBreakdown from '../components/TractBreakdown'
import FeedbackForm from '../components/FeedbackForm'
import CanvassTracker from '../components/CanvassTracker'
import { haversineKm, formatDistance } from '../utils/distance'
import { ZoneCardSkeleton } from '../components/SkeletonLoader'

// ---------- SVG Score Ring ----------

function ScoreRing({ score, band }: { score: number; band: string }) {
  const radius = 52
  const stroke = 8
  const circumference = 2 * Math.PI * radius
  const progress = (Math.min(score, 100) / 100) * circumference
  const colors = scoreColor(score)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <svg width={130} height={130} viewBox="0 0 130 130">
        <circle
          cx="65" cy="65" r={radius}
          fill="none" stroke="var(--border-primary)" strokeWidth={stroke}
        />
        <circle
          cx="65" cy="65" r={radius}
          fill="none" stroke={colors.fg} strokeWidth={stroke}
          strokeDasharray={`${progress} ${circumference - progress}`}
          strokeDashoffset={circumference * 0.25}
          strokeLinecap="round"
          style={{ transition: 'stroke-dasharray 0.6s ease' }}
        />
        <text x="65" y="60" textAnchor="middle" fontSize="28" fontWeight="700" fill="var(--text-primary)">
          {score.toFixed(1)}
        </text>
        <text x="65" y="80" textAnchor="middle" fontSize="12" fontWeight="600" fill={colors.fg}>
          {band.toUpperCase()}
        </text>
      </svg>
    </div>
  )
}

// ---------- Collapsible Section ----------

function Section({
  title, info, defaultOpen = true, accentBorder, children,
}: {
  title: string
  info?: string
  defaultOpen?: boolean
  accentBorder?: string
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div style={{
      background: 'var(--card-bg)',
      border: '1px solid var(--border-primary)',
      borderLeft: accentBorder ? `3px solid ${accentBorder}` : undefined,
      borderRadius: 10,
      marginBottom: 12,
      overflow: 'hidden',
    }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex', alignItems: 'center', width: '100%',
          padding: '12px 16px', border: 'none', cursor: 'pointer',
          background: 'transparent', textAlign: 'left',
        }}
      >
        <h3 style={{
          margin: 0, fontSize: 15, fontWeight: 600,
          color: accentBorder || 'var(--text-primary)',
          display: 'flex', alignItems: 'center', flex: 1,
        }}>
          {title}
          {info && <InfoTip text={info} />}
        </h3>
        <span style={{
          fontSize: 12, color: 'var(--text-tertiary)',
          transform: open ? 'rotate(0)' : 'rotate(-90deg)',
          transition: 'transform 0.2s',
        }}>
          ▾
        </span>
      </button>
      {open && <div style={{ padding: '0 16px 16px' }}>{children}</div>}
    </div>
  )
}

// ---------- Main Component ----------

export default function ZoneDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const isMobile = useMediaQuery('(max-width: 768px)')
  const homeLat = useAppStore((s) => s.homeLat)
  const homeLon = useAppStore((s) => s.homeLon)
  const toggleZoneInRoute = useAppStore((s) => s.toggleZoneInRoute)
  const routeZoneIds = useAppStore((s) => s.routeZoneIds)
  const [showFeedback, setShowFeedback] = useState(false)
  const [showCanvass, setShowCanvass] = useState(false)
  const [copied, setCopied] = useState(false)

  const { data: detail, isLoading, error } = useZoneDetail(id ?? null)

  const detailDistance = useMemo(() => {
    if (!detail || homeLat == null || homeLon == null) return null
    return haversineKm(homeLat, homeLon, detail.centroid_lat, detail.centroid_lon)
  }, [detail, homeLat, homeLon])

  const showStormSection = detail
    ? (detail.has_active_storm === true || detail.lead_type === 'storm_boosted' || detail.event_count > 0)
    : false

  const isInRoute = id ? routeZoneIds.includes(id) : false

  const handleShare = () => {
    navigator.clipboard.writeText(window.location.href)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // ---------- Loading / Error States ----------

  if (isLoading) {
    return (
      <div style={styles.page}>
        <div style={styles.container}>
          <ZoneCardSkeleton />
          <ZoneCardSkeleton />
          <ZoneCardSkeleton />
        </div>
      </div>
    )
  }

  if (error || !detail) {
    return (
      <div style={styles.page}>
        <div style={styles.container}>
          <button onClick={() => navigate('/')} style={styles.backBtn}>← Back to Dashboard</button>
          <p style={{ color: '#dc2626', fontSize: 14, marginTop: 24 }}>
            {error ? 'Failed to load zone details.' : 'Zone not found.'}
          </p>
        </div>
      </div>
    )
  }

  const colors = scoreColor(detail.composite_score)
  const gridCols = isMobile ? '1fr' : '1fr 1fr'

  return (
    <div style={styles.page}>
      {/* ===== Sticky Header ===== */}
      <div style={styles.header}>
        <div style={{ ...styles.container, display: 'flex', alignItems: 'center', gap: 10, padding: '0 16px' }}>
          <button onClick={() => navigate('/')} style={styles.headerBackBtn}>←</button>
          <span style={{
            fontSize: 12, fontWeight: 700, padding: '3px 10px', borderRadius: 6,
            background: colors.bg, color: colors.fg,
          }}>
            {detail.score_band.toUpperCase()}
          </span>
          <span style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)' }}>
            {detail.decay_adjusted_score.toFixed(1)}
          </span>
          <span style={{
            fontSize: 14, color: 'var(--text-secondary)', fontWeight: 500,
            flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {detail.display_name || detail.h3_index}
          </span>
          <button onClick={handleShare} style={styles.shareBtn}>
            {copied ? 'Copied!' : 'Share'}
          </button>
        </div>
      </div>

      {/* ===== Content ===== */}
      <div style={styles.container}>
        {/* Distance pill */}
        {detailDistance !== null && (
          <div style={{ fontSize: 13, color: 'var(--text-tertiary)', marginBottom: 12 }}>
            {formatDistance(detailDistance)} from home base
          </div>
        )}

        {/* ===== 1. Score Overview ===== */}
        <Section title="Score Overview" info="Composite lead quality score from 20+ data sources.">
          <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: 16, alignItems: 'center' }}>
            <ScoreRing score={detail.decay_adjusted_score} band={detail.score_band} />
            <div style={{ flex: 1, width: '100%' }}>
              {detail.base_score != null && (
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 4 }}>
                  Base score: <strong>{detail.base_score.toFixed(1)}</strong>
                  {showStormSection && detail.storm_boost != null && (
                    <span style={{
                      marginLeft: 8, fontSize: 12, fontWeight: 600, padding: '2px 6px', borderRadius: 4,
                      background: '#fff7ed', color: '#c2410c',
                    }}>
                      Storm +{detail.storm_boost.toFixed(0)}
                    </span>
                  )}
                </div>
              )}
              <SubScoreBar label="Roof Condition" value={detail.roof_condition} color="#e67e22" />
              <SubScoreBar label="Market Quality" value={detail.market_quality} color="#27ae60" />
              <SubScoreBar label="Risk Exposure" value={detail.risk_exposure} color="#e74c3c" />
              <SubScoreBar label="Canvass Efficiency" value={detail.canvass_efficiency} color="#3498db" />
            </div>
          </div>

          {/* Why This Score */}
          {detail.score_factors && detail.score_factors.length > 0 && (
            <>
              <h4 style={{ marginTop: 16, marginBottom: 8, fontSize: 14, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center' }}>
                Why This Score
                <InfoTip text="Top factors contributing to this zone's composite score. Bars show each factor's percentile rank; points show its weighted contribution." />
              </h4>
              <div style={{ background: 'var(--bg-secondary)', borderRadius: 8, padding: '10px 12px' }}>
                {detail.score_factors.map((factor, i) => {
                  const maxContribution = detail.score_factors![0].contribution
                  const barPct = maxContribution > 0 ? (factor.contribution / maxContribution) * 100 : 0
                  const fc = scoreColor(factor.percentile)
                  return (
                    <div key={factor.name} style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '5px 0',
                      borderBottom: i < detail.score_factors!.length - 1 ? '1px solid var(--border-primary)' : 'none',
                    }}>
                      <div style={{ width: isMobile ? 80 : 110, fontSize: 12, fontWeight: 500, color: 'var(--text-secondary)', flexShrink: 0 }}>
                        {factor.label}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-tertiary)', width: isMobile ? 40 : 55, textAlign: 'right', flexShrink: 0 }}>
                        {isMobile ? `${Math.round(factor.percentile)}%` : `${ordinal(factor.percentile)} pctile`}
                      </div>
                      <div style={{ flex: 1, height: 10, background: 'var(--bg-tertiary)', borderRadius: 5, overflow: 'hidden' }}>
                        <div style={{
                          width: `${barPct}%`, height: '100%',
                          background: fc.fg, borderRadius: 5,
                          transition: 'width 0.3s ease',
                        }} />
                      </div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: fc.fg, minWidth: 44, textAlign: 'right' }}>
                        {factor.contribution.toFixed(1)} pts
                      </div>
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </Section>

        {/* ===== 2. Neighborhood Breakdown ===== */}
        <Section title="Neighborhood Breakdown" info="Census tracts in this zone ranked by canvass priority based on demographics, housing age, and building density.">
          <TractBreakdown zoneId={id!} />
        </Section>

        {/* ===== 3. Roof Condition ===== */}
        <Section title="Roof Condition" info="Likelihood that roofs in this area need replacement based on age, climate exposure, and construction era.">
          <SubScoreBar label="Roof Condition Score" value={detail.roof_condition} color="#e67e22" />
          <div style={{ display: 'grid', gridTemplateColumns: gridCols, gap: 4 }}>
            {detail.avg_roof_age_years != null && (
              <Stat label="Avg Home Age" value={`${detail.avg_roof_age_years.toFixed(0)} yrs`}
                info="Average age of homes in the zone. Older roofs are more likely to need replacement." />
            )}
            {detail.dominant_decade != null && (
              <Stat label="Dominant Era" value={detail.dominant_decade}
                info="The most common decade homes were built." />
            )}
            {detail.climate_weathering_score != null && (
              <div style={{ padding: 8 }}>
                <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                  Climate Weathering
                  <InfoTip text="Index (0-100) of freeze-thaw cycles, UV exposure, rain, and wind." />
                </div>
                <ExposureBar score={detail.climate_weathering_score} />
              </div>
            )}
            {detail.avg_pct_built_before_1980 != null && (
              <Stat label="Pre-1980 Homes" value={`${detail.avg_pct_built_before_1980.toFixed(0)}%`}
                info="Older homes are more likely to need roof replacement." />
            )}
          </div>
        </Section>

        {/* ===== 4. Market Quality ===== */}
        <Section title="Market Quality" info="Homeowner willingness and ability to invest in roof replacement.">
          <SubScoreBar label="Market Quality Score" value={detail.market_quality} color="#27ae60" />
          <div style={{ display: 'grid', gridTemplateColumns: gridCols, gap: 4 }}>
            {detail.avg_median_income != null && (
              <Stat label="Median Income" value={`$${(detail.avg_median_income / 1000).toFixed(0)}k`}
                info="Higher income areas have homeowners more likely to afford and prioritize roof repairs." />
            )}
            {detail.avg_single_family_pct != null && (
              <Stat label="Owner Occupied" value={`${detail.avg_single_family_pct.toFixed(0)}%`}
                info="Percentage of owner-occupied single-family homes." />
            )}
            {detail.redfin_median_sale_price != null && (
              <Stat label="Median Sale Price" value={
                detail.redfin_median_sale_price >= 1_000_000
                  ? `$${(detail.redfin_median_sale_price / 1_000_000).toFixed(2)}M`
                  : `$${(detail.redfin_median_sale_price / 1000).toFixed(0)}k`
              }
                info="Redfin median home sale price." />
            )}
            {detail.hpi_5yr_change != null && (
              <Stat label="Home Price Trend" value={`${detail.hpi_5yr_change > 0 ? '+' : ''}${detail.hpi_5yr_change.toFixed(1)}%`}
                info="5-year home price change." />
            )}
          </div>
        </Section>

        {/* ===== 5. Risk Exposure ===== */}
        <Section title="Risk Exposure" info="Environmental and historical risk factors that increase roof damage likelihood.">
          <SubScoreBar label="Risk Exposure Score" value={detail.risk_exposure} color="#e74c3c" />
          <div style={{ display: 'grid', gridTemplateColumns: gridCols, gap: 4 }}>
            {detail.hail_exposure_score != null && (
              <div style={{ padding: 8 }}>
                <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                  Hail Exposure
                  <InfoTip text="Composite score (0-100) of historical hail severity and frequency." />
                </div>
                <ExposureBar score={detail.hail_exposure_score} />
              </div>
            )}
            {detail.fema_disaster_score != null && (
              <div style={{ padding: 8 }}>
                <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                  FEMA Score
                  <InfoTip text="Recency-weighted FEMA disaster score (0-100)." />
                </div>
                <ExposureBar score={detail.fema_disaster_score} />
              </div>
            )}
            {detail.tree_canopy_risk_score != null && (
              <div style={{ padding: 8 }}>
                <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                  Tree Canopy Risk
                  <InfoTip text="Risk score (0-100) from tree canopy density." />
                </div>
                <ExposureBar score={detail.tree_canopy_risk_score} />
              </div>
            )}
            {detail.verified_damage_5yr_usd != null && (
              <Stat
                label="Verified Damage (5yr)"
                value={detail.verified_damage_5yr_usd >= 1_000_000
                  ? `$${(detail.verified_damage_5yr_usd / 1_000_000).toFixed(1)}M`
                  : `$${(detail.verified_damage_5yr_usd / 1000).toFixed(0)}K`}
                info="NWS-verified property damage in the past 5 years."
              />
            )}
          </div>
          {/* FEMA Risk Index */}
          {(detail.nri_hail_risk || detail.nri_wind_risk || detail.nri_tornado_risk) && (
            <>
              <h4 style={{ margin: '12px 0 6px', fontSize: 13, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center' }}>
                FEMA Risk Index
                <InfoTip text="FEMA National Risk Index ratings for natural hazards." />
              </h4>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {detail.nri_hail_risk && <RiskBadge label="Hail" rating={detail.nri_hail_risk}
                  info="FEMA's assessment of hail risk frequency and severity." />}
                {detail.nri_wind_risk && <RiskBadge label="Wind" rating={detail.nri_wind_risk}
                  info="FEMA's assessment of straight-line wind risk." />}
                {detail.nri_tornado_risk && <RiskBadge label="Tornado" rating={detail.nri_tornado_risk}
                  info="FEMA's assessment of tornado risk." />}
              </div>
            </>
          )}
        </Section>

        {/* ===== 6. Canvass Efficiency ===== */}
        <Section title="Canvass Efficiency" info="How efficiently a canvassing team can cover this area.">
          <SubScoreBar label="Canvass Efficiency Score" value={detail.canvass_efficiency} color="#3498db" />
          <div style={{ display: 'grid', gridTemplateColumns: gridCols, gap: 4 }}>
            {detail.total_building_count != null && (
              <Stat label="Buildings" value={detail.total_building_count.toLocaleString()}
                info="Total building footprints in the zone." />
            )}
            {detail.avg_building_area_sqm != null && (
              <Stat label="Avg Bldg Size" value={`${detail.avg_building_area_sqm.toFixed(0)} m²`}
                info="Larger buildings typically mean bigger roofing jobs." />
            )}
            {detail.ruca_category != null && (
              <Stat label="Area Type" value={
                detail.ruca_category === 'urban' ? 'Urban' :
                detail.ruca_category === 'large_rural' ? 'Large Rural' :
                detail.ruca_category === 'small_town' ? 'Small Town' :
                detail.ruca_category === 'isolated_rural' ? 'Isolated Rural' :
                detail.ruca_category
              }
                info="USDA urban-rural classification." />
            )}
            <Stat label="Conversion" value={detail.predicted_conversion_rate ? `${(detail.predicted_conversion_rate * 100).toFixed(0)}%` : 'N/A'}
              info="Model-predicted likelihood that a lead in this zone converts to a signed roofing job." />
          </div>
        </Section>

        {/* ===== 7. Storm Activity (conditional) ===== */}
        {showStormSection && (
          <Section title="Active Storm Data" info="Recent severe weather activity boosting this zone's score." accentBorder="#f97316">
            {detail.storm_boost != null && (
              <SubScoreBar label="Storm Boost" value={detail.storm_boost} color="#f97316" />
            )}
            <div style={{ display: 'grid', gridTemplateColumns: gridCols, gap: 4 }}>
              <Stat label="Damage Prob" value={detail.damage_prob.toFixed(1)}
                info="Roof condition assessment boosted by active storm signals." />
              <Stat label="Events" value={String(detail.event_count)}
                info="Active severe weather events in this zone." />
              <Stat label="Max Hail" value={detail.max_hail_diameter ? `${detail.max_hail_diameter}"` : 'N/A'}
                info="Largest hailstone diameter observed." />
              <Stat label="Max Wind" value={detail.max_wind_speed ? `${detail.max_wind_speed} mph` : 'N/A'}
                info="Peak wind speed recorded." />
              <Stat label="Hours Ago" value={detail.hours_since_storm.toFixed(1)}
                info="Time since the most recent storm event." />
            </div>
            {detail.events.length > 0 && (
              <>
                <h4 style={{ margin: '12px 0 6px', fontSize: 13, color: 'var(--text-secondary)' }}>Storm Events</h4>
                {detail.events.map((evt) => (
                  <div key={evt.id} style={{
                    display: 'flex', gap: 8, alignItems: 'center', padding: '6px 8px',
                    background: 'var(--bg-secondary)', borderRadius: 6, marginBottom: 4,
                    fontSize: 13,
                  }}>
                    <span style={{
                      fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
                      background: '#fff7ed', color: '#c2410c',
                    }}>{evt.source.toUpperCase()}</span>
                    <span style={{ color: 'var(--text-primary)' }}>{evt.event_type}</span>
                    {evt.hail_diameter && <span style={{ color: 'var(--text-secondary)' }}>{evt.hail_diameter}" hail</span>}
                    {evt.wind_speed && <span style={{ color: 'var(--text-secondary)' }}>{evt.wind_speed} mph</span>}
                  </div>
                ))}
              </>
            )}
          </Section>
        )}

        {/* ===== 8. Area Intelligence (collapsed by default) ===== */}
        {(detail.avg_vacancy_rate != null || detail.pct_cost_burdened != null ||
          detail.redfin_median_dom != null || detail.redfin_price_drop_pct != null ||
          detail.bps_single_family_permits != null || detail.bps_total_value != null ||
          detail.ej_lead_paint != null || detail.ej_percentile != null ||
          detail.svi_overall != null || detail.flood_risk_category != null ||
          detail.age_clustering_score != null || detail.hail_events_3yr != null ||
          detail.fema_disaster_count != null) && (
          <Section title="Area Intelligence" info="Supplementary demographic and risk data." defaultOpen={false}>
            <div style={{ display: 'grid', gridTemplateColumns: gridCols, gap: 4 }}>
              {detail.avg_vacancy_rate != null && (
                <Stat label="Vacancy Rate" value={`${detail.avg_vacancy_rate.toFixed(1)}%`}
                  info="Lower vacancy means more occupied homes with owners who maintain their property." />
              )}
              {detail.pct_cost_burdened != null && (
                <Stat label="Cost Burdened" value={`${detail.pct_cost_burdened.toFixed(0)}%`}
                  info="% of homeowners spending 30%+ of income on housing." />
              )}
              {detail.redfin_median_dom != null && (
                <Stat label="Days on Market" value={`${detail.redfin_median_dom.toFixed(0)} days`}
                  info="Redfin median days on market." />
              )}
              {detail.redfin_price_drop_pct != null && (
                <Stat label="Price Drops" value={`${detail.redfin_price_drop_pct.toFixed(1)}%`}
                  info="Percentage of listings with price reductions." />
              )}
              {detail.hail_events_3yr != null && (
                <Stat label="Hail Events (3yr)" value={String(detail.hail_events_3yr)}
                  info="Radar-confirmed hail observations in the past 3 years." />
              )}
              {detail.fema_disaster_count != null && (
                <Stat label="FEMA Disasters" value={String(detail.fema_disaster_count)}
                  info="Number of FEMA disaster declarations in the area." />
              )}
              {detail.bps_single_family_permits != null && (
                <Stat label="New Construction" value={detail.bps_single_family_permits.toLocaleString()}
                  info="Annual single-family building permits in the county." />
              )}
              {detail.bps_total_value != null && detail.bps_total_value > 0 && (
                <Stat label="Permit Value" value={
                  detail.bps_total_value >= 1_000_000_000
                    ? `$${(detail.bps_total_value / 1_000_000_000).toFixed(1)}B`
                    : `$${(detail.bps_total_value / 1_000_000).toFixed(0)}M`
                }
                  info="Total annual construction value in the county." />
              )}
              {detail.ej_lead_paint != null && (
                <Stat label="Lead Paint Risk" value={`${detail.ej_lead_paint.toFixed(0)}%`}
                  info="EPA EJSCREEN: % of housing built before 1960." />
              )}
              {detail.age_clustering_score != null && (
                <div style={{ padding: 8 }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                    Age Clustering
                    <InfoTip text="How concentrated home ages are (0-100). High clustering means many homes built in the same era." />
                  </div>
                  <ExposureBar score={detail.age_clustering_score} />
                </div>
              )}
              {detail.ej_percentile != null && (
                <div style={{ padding: 8 }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                    EJ Burden
                    <InfoTip text="EPA Environmental Justice index percentile (0-100)." />
                  </div>
                  <ExposureBar score={detail.ej_percentile} />
                </div>
              )}
              {detail.flood_risk_category != null && (
                <Stat label="Flood Risk" value={
                  detail.flood_risk_category.charAt(0).toUpperCase() + detail.flood_risk_category.slice(1)
                }
                  info={`FEMA flood zone classification. ${detail.flood_insurance_required ? 'Flood insurance required.' : ''}`} />
              )}
              {detail.svi_overall != null && (
                <div style={{ padding: 8 }}>
                  <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase', display: 'flex', alignItems: 'center' }}>
                    Social Vulnerability
                    <InfoTip text="CDC Social Vulnerability Index. Higher scores indicate more vulnerable communities." />
                  </div>
                  <ExposureBar score={detail.svi_overall * 100} />
                </div>
              )}
            </div>
          </Section>
        )}

        {/* ===== Inline Feedback / Canvass ===== */}
        {showFeedback && (
          <div style={{ marginBottom: 12 }}>
            <FeedbackForm zoneId={id!} />
          </div>
        )}
        {showCanvass && (
          <div style={{ marginBottom: 12 }}>
            <CanvassTracker zoneId={id!} />
          </div>
        )}

        {/* Bottom spacer for sticky actions */}
        <div style={{ height: 72 }} />
      </div>

      {/* ===== Sticky Bottom Actions ===== */}
      <div style={styles.actions}>
        <div style={{ ...styles.container, display: 'flex', gap: 8, padding: '0 16px' }}>
          <button
            onClick={() => { setShowFeedback(!showFeedback); setShowCanvass(false) }}
            style={{
              ...styles.actionBtn,
              background: showFeedback ? 'var(--accent-blue)' : 'var(--bg-secondary)',
              color: showFeedback ? '#fff' : 'var(--text-primary)',
            }}
          >
            Feedback
          </button>
          <button
            onClick={() => { setShowCanvass(!showCanvass); setShowFeedback(false) }}
            style={{
              ...styles.actionBtn,
              background: showCanvass ? 'var(--accent-blue)' : 'var(--bg-secondary)',
              color: showCanvass ? '#fff' : 'var(--text-primary)',
            }}
          >
            Canvass
          </button>
          <button
            onClick={() => id && toggleZoneInRoute(id)}
            style={{
              ...styles.actionBtn,
              flex: 1,
              background: isInRoute ? '#16a34a' : 'var(--accent-blue)',
              color: '#fff',
            }}
          >
            {isInRoute ? 'In Route' : '+ Add to Route'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------- Styles ----------

const styles: Record<string, React.CSSProperties> = {
  page: {
    position: 'fixed',
    inset: 0,
    background: 'var(--bg-primary)',
    overflowY: 'auto',
    WebkitOverflowScrolling: 'touch',
  },
  container: {
    maxWidth: 720,
    margin: '0 auto',
    width: '100%',
  },
  header: {
    position: 'sticky',
    top: 0,
    zIndex: 50,
    background: 'var(--card-bg)',
    borderBottom: '1px solid var(--border-primary)',
    padding: '10px 0',
    backdropFilter: 'blur(8px)',
  },
  headerBackBtn: {
    background: 'none',
    border: 'none',
    fontSize: 20,
    cursor: 'pointer',
    color: 'var(--accent-blue)',
    padding: '4px 8px',
  },
  shareBtn: {
    fontSize: 12,
    fontWeight: 600,
    padding: '5px 12px',
    border: '1px solid var(--border-primary)',
    borderRadius: 6,
    background: 'var(--bg-secondary)',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    flexShrink: 0,
  },
  backBtn: {
    background: 'none',
    border: 'none',
    color: 'var(--accent-blue)',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    padding: '8px 0',
  },
  actions: {
    position: 'fixed',
    bottom: 0,
    left: 0,
    right: 0,
    background: 'var(--card-bg)',
    borderTop: '1px solid var(--border-primary)',
    padding: '10px 0',
    paddingBottom: 'max(10px, env(safe-area-inset-bottom))',
    zIndex: 50,
  },
  actionBtn: {
    padding: '10px 16px',
    border: 'none',
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
  },
}
