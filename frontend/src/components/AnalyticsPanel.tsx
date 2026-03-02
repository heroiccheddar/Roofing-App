import { useState } from 'react'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts'
import useAppStore from '../stores/appStore'
import { useAnalyticsDashboard } from '../hooks/useAnalytics'
import { LEAD_SOURCE_COLORS, LEAD_SOURCE_LABELS } from './ZoneDetailHelpers'
import type { LeaderboardPeriod, SourceBreakdown } from '../types/api'

type PeriodButton = { label: string; value: LeaderboardPeriod }

const PERIOD_BUTTONS: PeriodButton[] = [
  { label: 'Week', value: 'this_week' },
  { label: 'Month', value: 'this_month' },
  { label: 'All', value: 'all_time' },
]

// Interpolate between blue (#3b82f6) and green (#22c55e) by index fraction
function funnelStageColor(index: number, total: number): string {
  if (total <= 1) return '#3b82f6'
  const t = index / (total - 1)
  const r = Math.round(0x3b + t * (0x22 - 0x3b))
  const g = Math.round(0x82 + t * (0xc5 - 0x82))
  const b = Math.round(0xf6 + t * (0x5e - 0xf6))
  return `rgb(${r},${g},${b})`
}

interface KPICardProps {
  label: string
  value: string | number
  darkMode: boolean
}

function KPICard({ label, value, darkMode }: KPICardProps) {
  const cardBg = darkMode ? '#1e293b' : '#f8fafc'
  const cardBorder = darkMode ? '#334155' : '#e2e8f0'
  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'

  return (
    <div
      style={{
        background: cardBg,
        border: `1px solid ${cardBorder}`,
        borderRadius: 8,
        padding: '10px 12px',
      }}
    >
      <div style={{ fontSize: 11, color: textSecondary, marginBottom: 4, fontWeight: 500 }}>
        {label}
      </div>
      <div style={{ fontSize: 20, fontWeight: 700, color: textPrimary, lineHeight: 1 }}>
        {value}
      </div>
    </div>
  )
}

interface AnalyticsPanelProps {
  defaultExpanded?: boolean
}

export default function AnalyticsPanel({ defaultExpanded = false }: AnalyticsPanelProps) {
  const darkMode = useAppStore((s) => s.darkMode)
  const [expanded, setExpanded] = useState(defaultExpanded)
  const [period, setPeriod] = useState<LeaderboardPeriod>('this_week')

  const { data, isLoading, isError } = useAnalyticsDashboard(period)

  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'
  const borderColor = darkMode ? '#334155' : '#e2e8f0'
  const axisColor = darkMode ? '#94a3b8' : '#64748b'
  const tooltipBg = darkMode ? '#1e293b' : '#ffffff'
  const tooltipBorder = darkMode ? '#334155' : '#e2e8f0'
  const funnelBarBg = darkMode ? '#1e293b' : '#f1f5f9'

  const summary = data?.summary
  const daily_activity = data?.daily_activity ?? []
  const funnel = data?.funnel ?? []
  const maxCount = funnel.length > 0 ? Math.max(...funnel.map((s) => s.count), 1) : 1
  const source_breakdown: SourceBreakdown[] = data?.source_breakdown ?? []

  // Tick formatter: show day name for this_week, M/D for everything else
  function formatDateTick(dateStr: string): string {
    if (!dateStr) return ''
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return dateStr
    if (period === 'this_week') {
      return d.toLocaleDateString('en-US', { weekday: 'short' })
    }
    return `${d.getMonth() + 1}/${d.getDate()}`
  }

  return (
    <div style={{ borderBottom: `1px solid ${borderColor}` }}>
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '10px 16px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: textPrimary,
          fontSize: 14,
          fontWeight: 700,
        }}
      >
        <span>Analytics</span>
        <span style={{ fontSize: 11, color: textSecondary }}>
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {expanded && (
        <div style={{ padding: '0 16px 16px' }}>
          {/* Period selector */}
          <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
            {PERIOD_BUTTONS.map((btn) => {
              const selected = period === btn.value
              return (
                <button
                  key={btn.value}
                  onClick={() => setPeriod(btn.value)}
                  style={{
                    flex: 1,
                    padding: '5px 0',
                    borderRadius: 6,
                    border: selected ? '2px solid #2563eb' : `1px solid ${borderColor}`,
                    background: selected ? '#2563eb18' : 'transparent',
                    color: selected ? '#2563eb' : textSecondary,
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {btn.label}
                </button>
              )
            })}
          </div>

          {/* Loading state */}
          {isLoading && (
            <div style={{ fontSize: 13, color: textSecondary, textAlign: 'center', padding: '12px 0' }}>
              Loading...
            </div>
          )}

          {/* Error state */}
          {isError && !isLoading && (
            <div style={{ fontSize: 13, color: '#ef4444', textAlign: 'center', padding: '12px 0' }}>
              Failed to load analytics
            </div>
          )}

          {/* Content — only render when data is available */}
          {!isLoading && !isError && summary && (
            <>
              {/* KPI cards — 2x2 grid */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: 8,
                  marginBottom: 16,
                }}
              >
                <KPICard label="Total Pins" value={summary.total_pins} darkMode={darkMode} />
                <KPICard label="Contracts" value={summary.contracts_signed} darkMode={darkMode} />
                <KPICard
                  label="Conversion"
                  value={`${Math.round(summary.conversion_rate * 100)}%`}
                  darkMode={darkMode}
                />
                <KPICard
                  label="Avg/Day"
                  value={summary.avg_pins_per_day.toFixed(1)}
                  darkMode={darkMode}
                />
              </div>

              {/* Daily Activity bar chart */}
              <div style={{ marginBottom: 16 }}>
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: textSecondary,
                    marginBottom: 6,
                  }}
                >
                  Daily Activity
                </div>
                <ResponsiveContainer width="100%" height={140}>
                  <BarChart data={daily_activity} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 10, fill: axisColor }}
                      stroke={axisColor}
                      tickFormatter={formatDateTick}
                    />
                    <YAxis
                      width={30}
                      tick={{ fontSize: 10, fill: axisColor }}
                      stroke={axisColor}
                    />
                    <Bar
                      dataKey="pins_created"
                      fill="#3b82f6"
                      radius={[2, 2, 0, 0]}
                      name="Pins"
                    />
                    <Bar
                      dataKey="contracts_signed"
                      fill="#22c55e"
                      radius={[2, 2, 0, 0]}
                      name="Contracts"
                    />
                    <Tooltip
                      contentStyle={{
                        background: tooltipBg,
                        border: `1px solid ${tooltipBorder}`,
                        color: textPrimary,
                        fontSize: 12,
                        borderRadius: 6,
                      }}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Conversion funnel */}
              <div>
                <div
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: textSecondary,
                    marginBottom: 6,
                  }}
                >
                  Conversion Funnel
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {funnel.map((stage, index) => {
                    const stageColor = funnelStageColor(index, funnel.length)
                    const widthPct = maxCount > 0 ? (stage.count / maxCount) * 100 : 0
                    return (
                      <div key={stage.stage}>
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            marginBottom: 3,
                          }}
                        >
                          <span style={{ fontSize: 11, color: textSecondary }}>{stage.stage}</span>
                          <span style={{ fontSize: 11, fontWeight: 600, color: textPrimary }}>
                            {stage.count}
                          </span>
                        </div>
                        <div
                          style={{
                            background: funnelBarBg,
                            borderRadius: 4,
                            height: 8,
                            overflow: 'hidden',
                          }}
                        >
                          <div
                            style={{
                              width: `${widthPct}%`,
                              height: '100%',
                              background: stageColor,
                              borderRadius: 4,
                              transition: 'width 0.3s ease',
                            }}
                          />
                        </div>
                      </div>
                    )
                  })}
                  {funnel.length === 0 && (
                    <div
                      style={{ fontSize: 13, color: textSecondary, textAlign: 'center', padding: '8px 0' }}
                    >
                      No data for this period
                    </div>
                  )}
                </div>
              </div>

              {/* Lead Sources */}
              {source_breakdown.length > 0 && (
                <div style={{ marginTop: 20 }}>
                  <h4 style={{ fontSize: 13, fontWeight: 700, margin: '0 0 10px', color: textPrimary }}>
                    Lead Sources
                  </h4>
                  {source_breakdown.map((s) => {
                    const maxSourceCount = Math.max(...source_breakdown.map((x) => x.count))
                    const pct = maxSourceCount > 0 ? (s.count / maxSourceCount) * 100 : 0
                    const color = LEAD_SOURCE_COLORS[s.source] || '#94a3b8'
                    return (
                      <div key={s.source} style={{ marginBottom: 6 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 2 }}>
                          <span style={{ color: textSecondary }}>{LEAD_SOURCE_LABELS[s.source] || s.source}</span>
                          <span style={{ fontWeight: 600, color: textPrimary }}>{s.count}</span>
                        </div>
                        <div style={{ height: 6, borderRadius: 3, background: darkMode ? '#1e293b' : '#e2e8f0' }}>
                          <div style={{ height: '100%', borderRadius: 3, background: color, width: `${pct}%`, transition: 'width 0.3s' }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
