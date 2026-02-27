import { useState } from 'react'
import useAppStore from '../stores/appStore'
import { useLeaderboard } from '../hooks/useLeaderboard'
import type { LeaderboardPeriod } from '../types/api'

type PeriodButton = { label: string; value: LeaderboardPeriod }

const PERIOD_BUTTONS: PeriodButton[] = [
  { label: 'Week', value: 'this_week' },
  { label: 'Month', value: 'this_month' },
  { label: 'All', value: 'all_time' },
]

function rankCircleColor(rank: number): string {
  if (rank === 1) return '#f59e0b'
  if (rank === 2) return '#94a3b8'
  if (rank === 3) return '#cd7f32'
  return '#64748b'
}

export default function LeaderboardPanel() {
  const darkMode = useAppStore((s) => s.darkMode)
  const [expanded, setExpanded] = useState(false)
  const [period, setPeriod] = useState<LeaderboardPeriod>('this_week')

  const { data, isLoading, isError } = useLeaderboard(period)

  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'
  const borderColor = darkMode ? '#334155' : '#e2e8f0'

  const members = data?.members ?? []
  const currentUserId = data?.current_user_id ?? ''
  const isSolo = members.length <= 1

  const headerLabel = isSolo ? 'My Stats' : 'Leaderboard'

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
        <span>{headerLabel}</span>
        <span style={{ fontSize: 11, color: textSecondary }}>
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {expanded && (
        <div style={{ padding: '0 16px 12px' }}>
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
              Failed to load leaderboard
            </div>
          )}

          {/* Member list */}
          {!isLoading && !isError && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {members.map((member, index) => {
                const rank = index + 1
                const isCurrentUser = member.roofer_account_id === currentUserId
                const convPct = Math.round(member.conversion_rate * 100)

                return (
                  <div
                    key={member.roofer_account_id}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 10,
                      padding: '8px 10px',
                      borderRadius: 8,
                      border: isCurrentUser
                        ? '2px solid #2563eb'
                        : `1px solid ${borderColor}`,
                      background: isCurrentUser
                        ? (darkMode ? '#1e3a5f' : '#eff6ff')
                        : 'transparent',
                    }}
                  >
                    {/* Rank circle — hidden for solo users */}
                    {!isSolo && (
                      <span
                        style={{
                          width: 22,
                          height: 22,
                          borderRadius: '50%',
                          background: rankCircleColor(rank),
                          color: '#fff',
                          fontSize: 11,
                          fontWeight: 700,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0,
                          marginTop: 1,
                        }}
                      >
                        {rank}
                      </span>
                    )}

                    {/* Member info */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      {/* Company name + (you) label */}
                      <div style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: textPrimary,
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}>
                        {member.company_name}
                        {isCurrentUser && (
                          <span style={{
                            marginLeft: 6,
                            fontSize: 11,
                            fontWeight: 600,
                            color: '#2563eb',
                          }}>
                            (you)
                          </span>
                        )}
                      </div>

                      {/* Stats line */}
                      <div style={{
                        fontSize: 11,
                        color: textSecondary,
                        marginTop: 2,
                      }}>
                        {member.contract_signed} contracts | {member.total_pins} pins | {convPct}% conv
                      </div>
                    </div>
                  </div>
                )
              })}

              {members.length === 0 && (
                <div style={{ fontSize: 13, color: textSecondary, textAlign: 'center', padding: '8px 0' }}>
                  No data for this period
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
