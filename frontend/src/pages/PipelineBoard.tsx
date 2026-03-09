/**
 * PipelineBoard — full-screen Kanban view of all lead pins grouped by disposition.
 *
 * Columns map 1-to-1 to the LeadPinDisposition values and support HTML5
 * drag-and-drop to move a pin between stages. Moving a pin calls
 * updateLeadPin and invalidates the React Query cache so the board refreshes.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getAllLeadPins, updateLeadPin } from '../api/client'
import { DISPOSITION_LABELS, DISPOSITION_COLORS, LEAD_SOURCE_LABELS } from '../components/ZoneDetailHelpers'
import { showToast } from '../components/Toast'
import useAppStore from '../stores/appStore'
import { useMediaQuery } from '../hooks/useMediaQuery'
import type { LeadPinDisposition, LeadPinResponse, LeadPinSource } from '../types/api'

// ===== Column order =====

const COLUMN_ORDER: LeadPinDisposition[] = [
  'not_home',
  'callback',
  'interested',
  'inspection_set',
  'contract_signed',
  'not_interested',
]

const SOURCE_OPTIONS: (LeadPinSource | '')[] = ['', 'door_knock', 'referral', 'website', 'storm_canvass', 'other']

// ===== Helpers =====

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  return `${months}mo ago`
}

function formatCurrency(value: number): string {
  return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
}

// ===== Sub-components =====

interface PinCardProps {
  pin: LeadPinResponse
  darkMode: boolean
  isMobile: boolean
  onDragStart: (e: React.DragEvent, pinId: string, sourceDisposition: LeadPinDisposition) => void
  onChangeDisposition: (pinId: string, disposition: LeadPinDisposition) => void
}

function PinCard({ pin, darkMode, isMobile, onDragStart, onChangeDisposition }: PinCardProps) {
  const [showPicker, setShowPicker] = useState(false)
  const color = DISPOSITION_COLORS[pin.disposition] || '#94a3b8'

  return (
    <div
      draggable={!isMobile}
      onDragStart={isMobile ? undefined : (e) => onDragStart(e, pin.id, pin.disposition)}
      onClick={isMobile ? () => setShowPicker((v) => !v) : undefined}
      style={{
        background: darkMode ? '#0f172a' : '#ffffff',
        border: `1px solid ${darkMode ? '#1e293b' : '#e2e8f0'}`,
        borderRadius: 8,
        padding: '10px 12px',
        cursor: isMobile ? 'pointer' : 'grab',
        userSelect: 'none',
        marginBottom: 8,
        boxShadow: darkMode
          ? '0 1px 3px rgba(0,0,0,0.4)'
          : '0 1px 3px rgba(0,0,0,0.06)',
        transition: 'box-shadow 0.15s',
      }}
    >
      {/* Address row */}
      <div style={{
        fontSize: 13,
        fontWeight: 600,
        color: darkMode ? '#f1f5f9' : '#0f172a',
        marginBottom: 4,
        lineHeight: '1.3',
        wordBreak: 'break-word',
      }}>
        {pin.address || 'Dropped pin'}
      </div>

      {/* Contact name */}
      {pin.contact_name && (
        <div style={{
          fontSize: 12,
          color: darkMode ? '#94a3b8' : '#64748b',
          marginBottom: 4,
        }}>
          {pin.contact_name}
        </div>
      )}

      {/* Deal value */}
      {pin.estimated_value != null && pin.estimated_value > 0 && (
        <div style={{
          fontSize: 12,
          fontWeight: 600,
          color: '#22c55e',
          marginBottom: 4,
        }}>
          {formatCurrency(pin.estimated_value)}
        </div>
      )}

      {/* Footer: timestamp + disposition dot */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginTop: 6,
      }}>
        <span style={{ fontSize: 11, color: darkMode ? '#64748b' : '#94a3b8' }}>
          {timeAgo(pin.updated_at)}
        </span>
        <span style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          backgroundColor: color,
          flexShrink: 0,
        }} />
      </div>

      {/* Mobile disposition picker — tap card to reveal, tap pill to move */}
      {isMobile && showPicker && (
        <div style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 4,
          marginTop: 8,
          paddingTop: 8,
          borderTop: `1px solid ${darkMode ? '#334155' : '#e2e8f0'}`,
        }}>
          {COLUMN_ORDER.filter((d) => d !== pin.disposition).map((d) => (
            <button
              key={d}
              onClick={(e) => {
                e.stopPropagation()
                onChangeDisposition(pin.id, d)
                setShowPicker(false)
              }}
              style={{
                fontSize: 11,
                padding: '4px 8px',
                borderRadius: 12,
                border: 'none',
                background: (DISPOSITION_COLORS[d] || '#94a3b8') + '22',
                color: DISPOSITION_COLORS[d] || '#94a3b8',
                fontWeight: 600,
                cursor: 'pointer',
                minHeight: 28,
              }}
            >
              {DISPOSITION_LABELS[d] || d}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

interface KanbanColumnProps {
  disposition: LeadPinDisposition
  pins: LeadPinResponse[]
  totalValue: number
  isOver: boolean
  darkMode: boolean
  isMobile: boolean
  onDragStart: (e: React.DragEvent, pinId: string, sourceDisposition: LeadPinDisposition) => void
  onDragOver: (e: React.DragEvent, disposition: LeadPinDisposition) => void
  onDragLeave: () => void
  onDrop: (e: React.DragEvent, disposition: LeadPinDisposition) => void
  onChangeDisposition: (pinId: string, disposition: LeadPinDisposition) => void
}

function KanbanColumn({
  disposition,
  pins,
  totalValue,
  isOver,
  darkMode,
  isMobile,
  onDragStart,
  onDragOver,
  onDragLeave,
  onDrop,
  onChangeDisposition,
}: KanbanColumnProps) {
  const color = DISPOSITION_COLORS[disposition] || '#94a3b8'
  const label = DISPOSITION_LABELS[disposition] || disposition

  return (
    <div
      onDragOver={(e) => onDragOver(e, disposition)}
      onDragLeave={onDragLeave}
      onDrop={(e) => onDrop(e, disposition)}
      style={{
        width: 280,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        background: darkMode ? '#1e293b' : '#f8fafc',
        borderRadius: 10,
        border: isOver
          ? `2px solid ${color}`
          : `2px solid ${darkMode ? '#1e293b' : '#f8fafc'}`,
        transition: 'border-color 0.15s',
        overflow: 'hidden',
      }}
    >
      {/* Column header */}
      <div style={{
        padding: '10px 12px',
        borderBottom: `1px solid ${darkMode ? '#334155' : '#e2e8f0'}`,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        flexShrink: 0,
      }}>
        <span style={{
          width: 10,
          height: 10,
          borderRadius: '50%',
          backgroundColor: color,
          flexShrink: 0,
        }} />
        <span style={{
          fontSize: 13,
          fontWeight: 700,
          color: darkMode ? '#f1f5f9' : '#0f172a',
          flex: 1,
        }}>
          {label}
        </span>
        <span style={{
          fontSize: 12,
          fontWeight: 600,
          color: darkMode ? '#64748b' : '#94a3b8',
          background: darkMode ? '#0f172a' : '#e2e8f0',
          borderRadius: 10,
          padding: '1px 7px',
          minWidth: 20,
          textAlign: 'center',
        }}>
          {pins.length}
        </span>
        {totalValue > 0 && (
          <span style={{
            fontSize: 11,
            fontWeight: 600,
            color: '#22c55e',
            flexShrink: 0,
          }}>
            {formatCurrency(totalValue)}
          </span>
        )}
      </div>

      {/* Cards scroll area */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '10px 10px 4px',
        minHeight: 80,
      }}>
        {pins.length === 0 && (
          <div style={{
            fontSize: 12,
            color: darkMode ? '#475569' : '#cbd5e1',
            textAlign: 'center',
            paddingTop: 16,
            paddingBottom: 8,
          }}>
            No pins
          </div>
        )}
        {pins.map((pin) => (
          <PinCard
            key={pin.id}
            pin={pin}
            darkMode={darkMode}
            isMobile={isMobile}
            onDragStart={onDragStart}
            onChangeDisposition={onChangeDisposition}
          />
        ))}
      </div>
    </div>
  )
}

// ===== Main page =====

export default function PipelineBoard() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const darkMode = useAppStore((s) => s.darkMode)
  const isMobile = useMediaQuery('(max-width: 767px)')

  const [team, setTeam] = useState(false)
  const [search, setSearch] = useState('')
  const [sourceFilter, setSourceFilter] = useState<LeadPinSource | ''>('')
  const [dragOverColumn, setDragOverColumn] = useState<LeadPinDisposition | null>(null)

  // Drag state stored in refs via closure — avoids re-renders on every drag event
  const [dragState, setDragState] = useState<{
    pinId: string
    sourceDisposition: LeadPinDisposition
  } | null>(null)

  // ===== Data =====

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['pipeline-pins', team],
    queryFn: () => getAllLeadPins(team),
  })

  const mutation = useMutation({
    mutationFn: ({ pinId, disposition }: { pinId: string; disposition: LeadPinDisposition }) =>
      updateLeadPin(pinId, { disposition }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['pipeline-pins'] })
      showToast(`Moved to ${DISPOSITION_LABELS[variables.disposition] || variables.disposition}`)
    },
  })

  // ===== Filter & group pins =====

  let filtered = data?.pins || []

  if (search.trim()) {
    const q = search.trim().toLowerCase()
    filtered = filtered.filter((p) =>
      (p.address || '').toLowerCase().includes(q) ||
      (p.contact_name || '').toLowerCase().includes(q) ||
      (p.contact_email || '').toLowerCase().includes(q) ||
      (p.contact_phone || '').toLowerCase().includes(q)
    )
  }

  if (sourceFilter) {
    filtered = filtered.filter((p) => p.lead_source === sourceFilter)
  }

  const columns: Record<LeadPinDisposition, LeadPinResponse[]> = {
    not_home: [],
    callback: [],
    interested: [],
    inspection_set: [],
    contract_signed: [],
    not_interested: [],
  }

  for (const pin of filtered) {
    if (pin.disposition in columns) {
      columns[pin.disposition].push(pin)
    }
  }

  // ===== Drag-and-drop handlers =====

  function handleDragStart(
    e: React.DragEvent,
    pinId: string,
    sourceDisposition: LeadPinDisposition,
  ) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', pinId)
    setDragState({ pinId, sourceDisposition })
  }

  function handleDragOver(e: React.DragEvent, disposition: LeadPinDisposition) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOverColumn(disposition)
  }

  function handleDragLeave() {
    setDragOverColumn(null)
  }

  function handleDrop(e: React.DragEvent, targetDisposition: LeadPinDisposition) {
    e.preventDefault()
    setDragOverColumn(null)

    if (!dragState) return
    const { pinId, sourceDisposition } = dragState
    setDragState(null)

    // No-op if dropped in same column
    if (sourceDisposition === targetDisposition) return

    mutation.mutate({ pinId, disposition: targetDisposition })
  }

  function handleChangeDisposition(pinId: string, disposition: LeadPinDisposition) {
    mutation.mutate({ pinId, disposition })
  }

  // ===== Styles =====

  const headerBg = darkMode ? '#0f172a' : '#ffffff'
  const borderColor = darkMode ? '#1e293b' : '#e2e8f0'
  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'

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
        gap: 12,
        padding: '12px 16px',
        borderBottom: `1px solid ${borderColor}`,
        background: headerBg,
        flexShrink: 0,
      }}>
        {/* Close button */}
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
        }}>
          Pipeline Board
        </span>

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
        }}>
          <input
            type="checkbox"
            checked={team}
            onChange={(e) => setTeam(e.target.checked)}
            style={{ width: 15, height: 15, cursor: 'pointer' }}
          />
          Team View
        </label>

        {/* Total count (filtered) */}
        {data && (
          <span style={{
            fontSize: 12,
            color: textSecondary,
            flexShrink: 0,
          }}>
            {filtered.length} pin{filtered.length !== 1 ? 's' : ''}
            {filtered.length !== data.total && ` / ${data.total}`}
          </span>
        )}

        {/* Total pipeline value (filtered) */}
        {data && (() => {
          const totalValue = filtered.reduce((sum, p) => sum + (p.estimated_value || 0), 0)
          return totalValue > 0 ? (
            <span style={{ fontSize: 12, color: '#22c55e', fontWeight: 600, flexShrink: 0 }}>
              {formatCurrency(totalValue)} pipeline
            </span>
          ) : null
        })()}
      </div>

      {/* ===== Filter bar ===== */}
      {!isLoading && !isError && (
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
          {/* Search input */}
          <div style={{ position: 'relative', flex: isMobile ? '1 1 100%' : '0 1 220px' }}>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search address, contact..."
              style={{
                width: '100%',
                padding: '6px 28px 6px 10px',
                fontSize: 13,
                border: `1px solid ${borderColor}`,
                borderRadius: 6,
                background: darkMode ? '#0f172a' : '#ffffff',
                color: textPrimary,
                outline: 'none',
                minHeight: 34,
              }}
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                style={{
                  position: 'absolute',
                  right: 6,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: textSecondary,
                  fontSize: 14,
                  padding: '2px 4px',
                  lineHeight: 1,
                }}
              >
                &times;
              </button>
            )}
          </div>

          {/* Source filter pills */}
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
            {SOURCE_OPTIONS.map((src) => {
              const isActive = sourceFilter === src
              const label = src ? (LEAD_SOURCE_LABELS[src] || src) : 'All'
              return (
                <button
                  key={src || 'all'}
                  onClick={() => setSourceFilter(src)}
                  style={{
                    fontSize: 11,
                    padding: '4px 10px',
                    borderRadius: 12,
                    border: 'none',
                    background: isActive
                      ? (darkMode ? '#334155' : '#e2e8f0')
                      : 'transparent',
                    color: isActive ? textPrimary : textSecondary,
                    fontWeight: isActive ? 700 : 500,
                    cursor: 'pointer',
                    minHeight: 28,
                    transition: 'background 0.1s',
                  }}
                >
                  {label}
                </button>
              )
            })}
          </div>
        </div>
      )}

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
          Loading pipeline...
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
          {error instanceof Error ? error.message : 'Failed to load pipeline'}
        </div>
      )}

      {!isLoading && !isError && (
        <div style={{
          flex: 1,
          overflowX: 'auto',
          overflowY: 'hidden',
          padding: '16px',
        }}>
          <div style={{
            display: 'flex',
            gap: 12,
            height: '100%',
            // Ensure columns fill vertical space inside the scroll container
            alignItems: 'stretch',
          }}>
            {COLUMN_ORDER.map((disposition) => {
              const colPins = columns[disposition]
              const totalValue = colPins.reduce((sum, p) => sum + (p.estimated_value || 0), 0)
              return (
                <KanbanColumn
                  key={disposition}
                  disposition={disposition}
                  pins={colPins}
                  totalValue={totalValue}
                  isOver={dragOverColumn === disposition}
                  darkMode={darkMode}
                  isMobile={isMobile}
                  onDragStart={handleDragStart}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onChangeDisposition={handleChangeDisposition}
                />
              )
            })}
          </div>
        </div>
      )}

      {/* Mutation error toast */}
      {mutation.isError && (
        <div style={{
          position: 'absolute',
          bottom: 20,
          left: '50%',
          transform: 'translateX(-50%)',
          background: '#ef4444',
          color: '#fff',
          padding: '8px 16px',
          borderRadius: 8,
          fontSize: 13,
          fontWeight: 600,
          boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
          zIndex: 10,
        }}>
          {mutation.error instanceof Error
            ? mutation.error.message
            : 'Failed to update disposition'}
        </div>
      )}
    </div>
  )
}
