/**
 * CalendarView — day/week view of scheduled appointments and inspections.
 *
 * Shows all lead pins that have a callback_date set, grouped by day.
 * Supports day and week views with navigation. Clicking an event
 * navigates back to the dashboard and selects that pin.
 */

import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getLeadPinCallbacks } from '../api/client'
import { DISPOSITION_LABELS, DISPOSITION_COLORS } from '../components/ZoneDetailHelpers'
import useAppStore from '../stores/appStore'
import { useMediaQuery } from '../hooks/useMediaQuery'
import type { LeadPinResponse } from '../types/api'

// ===== Date helpers =====

/** Get Monday of the week containing `date`. */
function getMonday(date: Date): Date {
  const d = new Date(date)
  const day = d.getDay()
  const diff = day === 0 ? -6 : 1 - day
  d.setDate(d.getDate() + diff)
  d.setHours(0, 0, 0, 0)
  return d
}

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
}

function formatMonthYear(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

type ViewMode = 'day' | 'week'

// ===== Event card =====

interface EventCardProps {
  pin: LeadPinResponse
  darkMode: boolean
  onClick: () => void
}

function EventCard({ pin, darkMode, onClick }: EventCardProps) {
  const color = DISPOSITION_COLORS[pin.disposition] || '#94a3b8'
  const label = DISPOSITION_LABELS[pin.disposition] || pin.disposition
  const time = pin.callback_date ? formatTime(new Date(pin.callback_date)) : ''

  // Check if overdue
  const isOverdue = pin.callback_date ? new Date(pin.callback_date) < new Date() : false

  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 10,
        padding: '10px 12px',
        background: darkMode ? '#0f172a' : '#ffffff',
        border: `1px solid ${isOverdue ? '#ef4444' : darkMode ? '#1e293b' : '#e2e8f0'}`,
        borderLeft: `3px solid ${color}`,
        borderRadius: 8,
        cursor: 'pointer',
        width: '100%',
        textAlign: 'left',
        marginBottom: 6,
        transition: 'box-shadow 0.15s',
        boxShadow: darkMode
          ? '0 1px 3px rgba(0,0,0,0.3)'
          : '0 1px 3px rgba(0,0,0,0.06)',
      }}
    >
      {/* Time column */}
      <div style={{
        fontSize: 12,
        fontWeight: 600,
        color: isOverdue ? '#ef4444' : darkMode ? '#94a3b8' : '#64748b',
        minWidth: 60,
        flexShrink: 0,
        paddingTop: 1,
      }}>
        {time || 'All day'}
      </div>

      {/* Details */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 13,
          fontWeight: 600,
          color: darkMode ? '#f1f5f9' : '#0f172a',
          lineHeight: '1.3',
          wordBreak: 'break-word',
        }}>
          {pin.address || 'Dropped pin'}
        </div>

        {pin.contact_name && (
          <div style={{
            fontSize: 12,
            color: darkMode ? '#94a3b8' : '#64748b',
            marginTop: 2,
          }}>
            {pin.contact_name}
          </div>
        )}

        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          marginTop: 4,
        }}>
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
            fontSize: 11,
            fontWeight: 600,
            color,
            background: `${color}18`,
            padding: '1px 8px',
            borderRadius: 10,
          }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: color }} />
            {label}
          </span>
          {isOverdue && (
            <span style={{
              fontSize: 11,
              fontWeight: 600,
              color: '#ef4444',
            }}>
              Overdue
            </span>
          )}
          {pin.estimated_value != null && pin.estimated_value > 0 && (
            <span style={{
              fontSize: 11,
              fontWeight: 600,
              color: '#22c55e',
            }}>
              ${pin.estimated_value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            </span>
          )}
        </div>
      </div>
    </button>
  )
}

// ===== Day column (used in week view) =====

interface DayColumnProps {
  date: Date
  pins: LeadPinResponse[]
  darkMode: boolean
  isToday: boolean
  onPinClick: (pinId: string) => void
}

function DayColumn({ date, pins, darkMode, isToday, onPinClick }: DayColumnProps) {
  return (
    <div style={{
      flex: 1,
      minWidth: 180,
      display: 'flex',
      flexDirection: 'column',
      borderRight: `1px solid ${darkMode ? '#1e293b' : '#e2e8f0'}`,
    }}>
      {/* Day header */}
      <div style={{
        padding: '8px 10px',
        borderBottom: `1px solid ${darkMode ? '#1e293b' : '#e2e8f0'}`,
        textAlign: 'center',
        flexShrink: 0,
        background: isToday
          ? (darkMode ? '#1e3a5f' : '#eff6ff')
          : 'transparent',
      }}>
        <div style={{
          fontSize: 11,
          fontWeight: 600,
          color: isToday ? 'var(--accent-blue)' : (darkMode ? '#64748b' : '#94a3b8'),
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
        }}>
          {date.toLocaleDateString('en-US', { weekday: 'short' })}
        </div>
        <div style={{
          fontSize: 18,
          fontWeight: 700,
          color: isToday ? 'var(--accent-blue)' : (darkMode ? '#f1f5f9' : '#0f172a'),
          marginTop: 2,
        }}>
          {date.getDate()}
        </div>
      </div>

      {/* Events */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '8px 6px',
      }}>
        {pins.length === 0 && (
          <div style={{
            fontSize: 12,
            color: darkMode ? '#475569' : '#cbd5e1',
            textAlign: 'center',
            paddingTop: 12,
          }}>
            No events
          </div>
        )}
        {pins.map((pin) => (
          <EventCard
            key={pin.id}
            pin={pin}
            darkMode={darkMode}
            onClick={() => onPinClick(pin.id)}
          />
        ))}
      </div>
    </div>
  )
}

// ===== Main page =====

export default function CalendarView() {
  const navigate = useNavigate()
  const darkMode = useAppStore((s) => s.darkMode)
  const isMobile = useMediaQuery('(max-width: 767px)')
  const setSelectedLeadPinId = useAppStore((s) => s.setSelectedLeadPinId)

  const [viewMode, setViewMode] = useState<ViewMode>('week')
  const [currentDate, setCurrentDate] = useState(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  })
  const [team, setTeam] = useState(false)

  const today = useMemo(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  }, [])

  // ===== Data =====

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['calendar-pins', team],
    queryFn: () => getLeadPinCallbacks(team),
  })

  // ===== Computed =====

  const weekDays = useMemo(() => {
    const monday = getMonday(currentDate)
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(monday)
      d.setDate(monday.getDate() + i)
      return d
    })
  }, [currentDate])

  // Group pins by date
  const pinsByDate = useMemo(() => {
    const map = new Map<string, LeadPinResponse[]>()
    if (!data?.pins) return map

    for (const pin of data.pins) {
      if (!pin.callback_date) continue
      const d = new Date(pin.callback_date)
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
      const arr = map.get(key) || []
      arr.push(pin)
      map.set(key, arr)
    }

    // Sort each day's pins by time
    for (const [, pins] of map) {
      pins.sort((a, b) => new Date(a.callback_date!).getTime() - new Date(b.callback_date!).getTime())
    }

    return map
  }, [data])

  function getPinsForDate(date: Date): LeadPinResponse[] {
    const key = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
    return pinsByDate.get(key) || []
  }

  // Count events in current view
  const viewEventCount = useMemo(() => {
    if (viewMode === 'day') {
      return getPinsForDate(currentDate).length
    }
    return weekDays.reduce((sum, d) => sum + getPinsForDate(d).length, 0)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode, currentDate, weekDays, pinsByDate])

  // ===== Navigation =====

  function goToday() {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    setCurrentDate(d)
  }

  function goPrev() {
    const d = new Date(currentDate)
    d.setDate(d.getDate() - (viewMode === 'week' ? 7 : 1))
    setCurrentDate(d)
  }

  function goNext() {
    const d = new Date(currentDate)
    d.setDate(d.getDate() + (viewMode === 'week' ? 7 : 1))
    setCurrentDate(d)
  }

  function handlePinClick(pinId: string) {
    setSelectedLeadPinId(pinId)
    navigate('/')
  }

  // ===== Styles =====

  const headerBg = darkMode ? '#0f172a' : '#ffffff'
  const borderColor = darkMode ? '#1e293b' : '#e2e8f0'
  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'

  // ===== Title =====

  const title = viewMode === 'week'
    ? formatMonthYear(weekDays[0])
    : currentDate.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })

  // ===== Render =====

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 200,
      background: darkMode ? '#0a1628' : '#f1f5f9',
      color: textPrimary,
      fontFamily: 'system-ui, -apple-system, sans-serif',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* ===== Header ===== */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '10px 16px',
        borderBottom: `1px solid ${borderColor}`,
        background: headerBg,
        flexShrink: 0,
        flexWrap: 'wrap',
      }}>
        {/* Back button */}
        <button
          onClick={() => navigate('/')}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--accent-blue)',
            fontSize: 15,
            fontWeight: 600,
            cursor: 'pointer',
            padding: '8px 12px',
            minHeight: 44,
            flexShrink: 0,
          }}
        >
          &larr; Back
        </button>

        {/* Title */}
        <span style={{
          fontWeight: 700,
          fontSize: 16,
          color: textPrimary,
          flex: 1,
          minWidth: 140,
        }}>
          {title}
        </span>

        {/* Nav buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
          <button onClick={goPrev} style={{
            background: 'none', border: `1px solid ${borderColor}`, borderRadius: 6,
            padding: isMobile ? '8px 14px' : '4px 10px', fontSize: 14, cursor: 'pointer', color: textSecondary,
            fontWeight: 600, minHeight: isMobile ? 44 : undefined, minWidth: isMobile ? 44 : undefined,
          }}>
            &lsaquo;
          </button>
          <button onClick={goToday} style={{
            background: 'none', border: `1px solid ${borderColor}`, borderRadius: 6,
            padding: isMobile ? '8px 14px' : '4px 10px', fontSize: 12, cursor: 'pointer', color: textSecondary,
            fontWeight: 600, minHeight: isMobile ? 44 : undefined,
          }}>
            Today
          </button>
          <button onClick={goNext} style={{
            background: 'none', border: `1px solid ${borderColor}`, borderRadius: 6,
            padding: isMobile ? '8px 14px' : '4px 10px', fontSize: 14, cursor: 'pointer', color: textSecondary,
            fontWeight: 600, minHeight: isMobile ? 44 : undefined, minWidth: isMobile ? 44 : undefined,
          }}>
            &rsaquo;
          </button>
        </div>

        {/* View mode toggle */}
        <div style={{
          display: 'flex',
          border: `1px solid ${borderColor}`,
          borderRadius: 6,
          overflow: 'hidden',
          flexShrink: 0,
        }}>
          {(['day', 'week'] as ViewMode[]).map((mode) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              style={{
                padding: isMobile ? '8px 16px' : '4px 12px',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                border: 'none',
                background: viewMode === mode
                  ? (darkMode ? '#334155' : '#e2e8f0')
                  : 'transparent',
                color: viewMode === mode ? textPrimary : textSecondary,
                minHeight: isMobile ? 44 : undefined,
              }}
            >
              {mode.charAt(0).toUpperCase() + mode.slice(1)}
            </button>
          ))}
        </div>

        {/* Team toggle */}
        <label style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 13,
          fontWeight: 600,
          color: textSecondary,
          cursor: 'pointer',
          flexShrink: 0,
          minHeight: isMobile ? 44 : undefined,
          padding: isMobile ? '4px 0' : undefined,
        }}>
          <input
            type="checkbox"
            checked={team}
            onChange={(e) => setTeam(e.target.checked)}
            style={{ width: isMobile ? 18 : 15, height: isMobile ? 18 : 15, cursor: 'pointer' }}
          />
          Team
        </label>

        {/* Event count */}
        <span style={{
          fontSize: 12,
          color: textSecondary,
          flexShrink: 0,
        }}>
          {viewEventCount} event{viewEventCount !== 1 ? 's' : ''}
        </span>
      </div>

      {/* ===== Body ===== */}
      {isLoading && (
        <div style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: textSecondary,
          fontSize: 14,
        }}>
          Loading calendar...
        </div>
      )}

      {isError && (
        <div style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#ef4444',
          fontSize: 14,
        }}>
          {error instanceof Error ? error.message : 'Failed to load events'}
        </div>
      )}

      {!isLoading && !isError && viewMode === 'week' && (
        <div style={{
          flex: 1,
          display: 'flex',
          overflow: 'hidden',
        }}>
          {weekDays.map((date) => (
            <DayColumn
              key={date.toISOString()}
              date={date}
              pins={getPinsForDate(date)}
              darkMode={darkMode}
              isToday={isSameDay(date, today)}
              onPinClick={handlePinClick}
            />
          ))}
        </div>
      )}

      {!isLoading && !isError && viewMode === 'day' && (
        <div style={{
          flex: 1,
          overflowY: 'auto',
          padding: 16,
          maxWidth: 640,
          margin: '0 auto',
          width: '100%',
        }}>
          {/* Day header */}
          <div style={{
            textAlign: 'center',
            marginBottom: 16,
          }}>
            <div style={{
              fontSize: 13,
              fontWeight: 600,
              color: isSameDay(currentDate, today) ? 'var(--accent-blue)' : textSecondary,
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
            }}>
              {currentDate.toLocaleDateString('en-US', { weekday: 'long' })}
            </div>
            <div style={{
              fontSize: 32,
              fontWeight: 700,
              color: isSameDay(currentDate, today) ? 'var(--accent-blue)' : textPrimary,
              marginTop: 4,
            }}>
              {currentDate.getDate()}
            </div>
          </div>

          {/* Events */}
          {getPinsForDate(currentDate).length === 0 && (
            <div style={{
              textAlign: 'center',
              color: textSecondary,
              fontSize: 14,
              paddingTop: 40,
            }}>
              No events scheduled for this day
            </div>
          )}
          {getPinsForDate(currentDate).map((pin) => (
            <EventCard
              key={pin.id}
              pin={pin}
              darkMode={darkMode}
              onClick={() => handlePinClick(pin.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
