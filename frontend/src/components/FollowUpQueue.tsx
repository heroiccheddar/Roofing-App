import { useState } from 'react'
import useAppStore from '../stores/appStore'
import { useLeadPinCallbacks } from '../hooks/useLeadPins'
import { DispositionBadge } from './ZoneDetailHelpers'

function callbackTimeLabel(dateStr: string | undefined): { text: string; color: string } {
  if (!dateStr) return { text: 'no date set', color: '#94a3b8' }
  const now = new Date()
  const target = new Date(dateStr)
  const diffMs = target.getTime() - now.getTime()
  const diffHours = diffMs / (1000 * 60 * 60)
  const diffDays = Math.round(diffHours / 24)

  if (diffHours < -24) return { text: `overdue ${Math.abs(diffDays)}d`, color: '#ef4444' }
  if (diffHours < 0) return { text: 'overdue today', color: '#ef4444' }
  if (diffHours < 24) return { text: 'today', color: '#f59e0b' }
  if (diffHours < 48) return { text: 'tomorrow', color: '#22c55e' }
  return { text: `in ${diffDays}d`, color: '#94a3b8' }
}

export default function FollowUpQueue() {
  const darkMode = useAppStore((s) => s.darkMode)
  const setFlyToCoords = useAppStore((s) => s.setFlyToCoords)
  const setSelectedLeadPinId = useAppStore((s) => s.setSelectedLeadPinId)
  const { data, isLoading } = useLeadPinCallbacks()

  const [expanded, setExpanded] = useState(true)

  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'
  const borderColor = darkMode ? '#334155' : '#e2e8f0'

  const pins = data?.pins ?? []
  const count = pins.length

  // Auto-collapse if empty
  if (count === 0 && !isLoading) {
    return (
      <div style={{
        padding: '10px 16px',
        borderBottom: `1px solid ${borderColor}`,
        fontSize: 13,
        color: textSecondary,
      }}>
        No follow-ups scheduled
      </div>
    )
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
        <span>Follow-Ups {count > 0 && `(${count})`}</span>
        <span style={{ fontSize: 11, color: textSecondary }}>
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {/* List */}
      {expanded && (
        <div style={{ maxHeight: 240, overflowY: 'auto' }}>
          {isLoading && (
            <div style={{ padding: 16, fontSize: 13, color: textSecondary, textAlign: 'center' }}>
              Loading...
            </div>
          )}
          {pins.map((pin) => {
            const { text, color } = callbackTimeLabel(pin.callback_date)
            return (
              <button
                key={pin.id}
                onClick={() => {
                  setFlyToCoords({ lat: pin.lat, lon: pin.lon, zoom: 16 })
                  setSelectedLeadPinId(pin.id)
                }}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '8px 16px',
                  background: 'transparent',
                  border: 'none',
                  borderTop: `1px solid ${borderColor}`,
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: textPrimary,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}>
                    {pin.address || 'Dropped pin'}
                  </div>
                  <div style={{ fontSize: 11, color, fontWeight: 600, marginTop: 2 }}>
                    {text}
                  </div>
                </div>
                <DispositionBadge disposition={pin.disposition} />
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
