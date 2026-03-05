/**
 * NotificationCenter — bell icon with badge + dropdown feed.
 *
 * Aggregates storm alerts (from /alerts/history) and overdue callbacks
 * (from /leads/callbacks) into a unified notification feed. Unread badge
 * shows count of unopened alerts + overdue callbacks.
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAlertHistory, getLeadPinCallbacks, markAlertOpened } from '../api/client'
import useAppStore from '../stores/appStore'
import type { AlertLogResponse, LeadPinResponse } from '../types/api'

// ===== Helpers =====

type NotificationItem =
  | { kind: 'alert'; date: Date; data: AlertLogResponse }
  | { kind: 'callback'; date: Date; data: LeadPinResponse }

function timeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function overdueDays(callbackDate: Date): number {
  return Math.max(0, Math.floor((Date.now() - callbackDate.getTime()) / (1000 * 60 * 60 * 24)))
}

// ===== Component =====

export default function NotificationCenter() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const darkMode = useAppStore((s) => s.darkMode)
  const setSelectedLeadPinId = useAppStore((s) => s.setSelectedLeadPinId)

  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // ===== Data =====

  const { data: alertData } = useQuery({
    queryKey: ['alertHistory'],
    queryFn: getAlertHistory,
    staleTime: 2 * 60 * 1000,
  })

  const { data: callbackData } = useQuery({
    queryKey: ['leadPinCallbacks'],
    queryFn: () => getLeadPinCallbacks(),
    staleTime: 60 * 1000,
  })

  const markOpened = useMutation({
    mutationFn: markAlertOpened,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alertHistory'] }),
  })

  // ===== Build unified feed =====

  const now = new Date()

  const alertItems: NotificationItem[] = (alertData?.alerts || []).map((a) => ({
    kind: 'alert' as const,
    date: new Date(a.sent_at),
    data: a,
  }))

  const overdueCallbacks: NotificationItem[] = (callbackData?.pins || [])
    .filter((p) => p.callback_date && new Date(p.callback_date) < now)
    .map((p) => ({
      kind: 'callback' as const,
      date: new Date(p.callback_date!),
      data: p,
    }))

  const items: NotificationItem[] = [...alertItems, ...overdueCallbacks]
    .sort((a, b) => b.date.getTime() - a.date.getTime())
    .slice(0, 30)

  // ===== Unread count =====

  const unreadAlerts = (alertData?.alerts || []).filter((a) => !a.opened_at).length
  const unreadCallbacks = overdueCallbacks.length
  const unreadCount = unreadAlerts + unreadCallbacks

  // ===== Click outside to close =====

  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
      setOpen(false)
    }
  }, [])

  useEffect(() => {
    if (open) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [open, handleClickOutside])

  // ===== Handlers =====

  function handleAlertClick(alert: AlertLogResponse) {
    if (!alert.opened_at) {
      markOpened.mutate(alert.id)
    }
    setOpen(false)
    navigate(`/zones/${alert.lead_zone_id}`)
  }

  function handleCallbackClick(pin: LeadPinResponse) {
    setOpen(false)
    setSelectedLeadPinId(pin.id)
  }

  function handleMarkAllRead() {
    const unopened = (alertData?.alerts || []).filter((a) => !a.opened_at)
    for (const alert of unopened) {
      markOpened.mutate(alert.id)
    }
  }

  // ===== Styles =====

  const dropdownBg = darkMode ? '#1e293b' : '#ffffff'
  const itemBg = darkMode ? '#0f172a' : '#f8fafc'
  const borderColor = darkMode ? '#334155' : '#e2e8f0'
  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      {/* Bell button */}
      <button
        onClick={() => setOpen((v) => !v)}
        title="Notifications"
        style={{
          background: 'none',
          border: '1px solid var(--border-primary)',
          width: 28,
          height: 28,
          borderRadius: '50%',
          cursor: 'pointer',
          color: 'var(--text-secondary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 0,
          flexShrink: 0,
          position: 'relative',
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>

        {/* Badge */}
        {unreadCount > 0 && (
          <span
            style={{
              position: 'absolute',
              top: -4,
              right: -4,
              background: '#ef4444',
              color: '#fff',
              fontSize: 9,
              fontWeight: 700,
              borderRadius: 10,
              minWidth: 16,
              height: 16,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '0 4px',
              lineHeight: 1,
            }}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div
          style={{
            position: 'absolute',
            top: 36,
            right: 0,
            width: 360,
            maxHeight: 420,
            background: dropdownBg,
            border: `1px solid ${borderColor}`,
            borderRadius: 12,
            boxShadow: darkMode
              ? '0 8px 24px rgba(0,0,0,0.5)'
              : '0 8px 24px rgba(0,0,0,0.12)',
            zIndex: 300,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Header */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '12px 16px',
              borderBottom: `1px solid ${borderColor}`,
              flexShrink: 0,
            }}
          >
            <span style={{ fontWeight: 700, fontSize: 14, color: textPrimary }}>
              Notifications
            </span>
            {unreadAlerts > 0 && (
              <button
                onClick={handleMarkAllRead}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--accent-blue)',
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: 'pointer',
                  padding: '4px 8px',
                }}
              >
                Mark all read
              </button>
            )}
          </div>

          {/* Items */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {items.length === 0 && (
              <div
                style={{
                  padding: '40px 16px',
                  textAlign: 'center',
                  color: textSecondary,
                  fontSize: 13,
                }}
              >
                No notifications
              </div>
            )}

            {items.map((item, i) => {
              if (item.kind === 'alert') {
                const alert = item.data
                const isUnread = !alert.opened_at
                return (
                  <button
                    key={`alert-${alert.id}`}
                    onClick={() => handleAlertClick(alert)}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 10,
                      padding: '10px 16px',
                      background: isUnread ? itemBg : 'transparent',
                      border: 'none',
                      borderBottom: i < items.length - 1 ? `1px solid ${borderColor}` : 'none',
                      borderLeft: isUnread ? '3px solid #f59e0b' : '3px solid transparent',
                      cursor: 'pointer',
                      textAlign: 'left',
                    }}
                  >
                    {/* Lightning icon */}
                    <div
                      style={{
                        width: 28,
                        height: 28,
                        borderRadius: '50%',
                        background: '#f59e0b22',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                        marginTop: 2,
                      }}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                      </svg>
                    </div>

                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: 13,
                        fontWeight: isUnread ? 700 : 500,
                        color: textPrimary,
                        lineHeight: '1.3',
                      }}>
                        Storm Alert{alert.zone_h3_index ? ` — ${alert.zone_h3_index.slice(0, 8)}` : ''}
                      </div>
                      <div style={{
                        fontSize: 11,
                        color: textSecondary,
                        marginTop: 2,
                      }}>
                        {alert.zone_score != null && `Score: ${(alert.zone_score * 100).toFixed(0)}%`}
                        {alert.zone_score != null && ' · '}
                        {timeAgo(item.date)}
                      </div>
                    </div>
                  </button>
                )
              }

              // Overdue callback
              const pin = item.data
              const days = overdueDays(item.date)
              return (
                <button
                  key={`cb-${pin.id}`}
                  onClick={() => handleCallbackClick(pin)}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 10,
                    padding: '10px 16px',
                    background: itemBg,
                    border: 'none',
                    borderBottom: i < items.length - 1 ? `1px solid ${borderColor}` : 'none',
                    borderLeft: '3px solid #ef4444',
                    cursor: 'pointer',
                    textAlign: 'left',
                  }}
                >
                  {/* Phone icon */}
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: '50%',
                      background: '#ef444422',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      marginTop: 2,
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
                    </svg>
                  </div>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: 13,
                      fontWeight: 700,
                      color: textPrimary,
                      lineHeight: '1.3',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {pin.contact_name || pin.address || 'Callback'}
                    </div>
                    <div style={{
                      fontSize: 11,
                      color: '#ef4444',
                      marginTop: 2,
                      fontWeight: 600,
                    }}>
                      {days === 0 ? 'Overdue today' : `Overdue by ${days}d`}
                      <span style={{ color: textSecondary, fontWeight: 400 }}>
                        {' · '}{item.date.toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
