/**
 * LeadPinPanel — UI for the Lead Pins + Dispositions feature.
 *
 * Responsibilities:
 *  - Pin-drop mode toggle button
 *  - Disposition picker modal (new pin or update existing)
 *  - Pin list for current viewport
 *  - Pin detail with activity timeline
 *  - Delete pin with confirmation
 */

import { useState } from 'react'
import useAppStore from '../stores/appStore'
import { useLeadPins, useUpdateLeadPin, useDeleteLeadPin, useLeadPinActivities, useCreatePinActivity } from '../hooks/useLeadPins'
import { DispositionBadge, DISPOSITION_COLORS, DISPOSITION_LABELS } from './ZoneDetailHelpers'
import type { LeadPinDisposition, LeadPinResponse } from '../types/api'

// ===== Helpers =====

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  if (days < 30) return `${days}d ago`
  return new Date(dateStr).toLocaleDateString()
}

const DISPOSITION_ORDER: LeadPinDisposition[] = [
  'not_home',
  'callback',
  'interested',
  'inspection_set',
  'contract_signed',
  'not_interested',
]

// ===== Disposition Picker =====

interface DispositionPickerProps {
  initialDisposition?: LeadPinDisposition
  initialNotes?: string
  title: string
  onConfirm: (disposition: LeadPinDisposition, notes: string) => void
  onCancel: () => void
  isLoading?: boolean
}

export function DispositionPicker({
  initialDisposition,
  initialNotes = '',
  title,
  onConfirm,
  onCancel,
  isLoading = false,
}: DispositionPickerProps) {
  const [selected, setSelected] = useState<LeadPinDisposition>(
    initialDisposition ?? 'not_home',
  )
  const [notes, setNotes] = useState(initialNotes)
  const darkMode = useAppStore((s) => s.darkMode)

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0,0,0,0.45)',
      zIndex: 200,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '16px',
    }}>
      <div style={{
        background: darkMode ? '#1e293b' : '#ffffff',
        borderRadius: 12,
        padding: 20,
        width: '100%',
        maxWidth: 360,
        boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
      }}>
        <h3 style={{
          margin: '0 0 16px',
          fontSize: 16,
          fontWeight: 700,
          color: darkMode ? '#f1f5f9' : '#0f172a',
        }}>
          {title}
        </h3>

        {/* 2x3 disposition grid */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 8,
          marginBottom: 16,
        }}>
          {DISPOSITION_ORDER.map((d) => {
            const color = DISPOSITION_COLORS[d]
            const isActive = selected === d
            return (
              <button
                key={d}
                onClick={() => setSelected(d)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '10px 12px',
                  borderRadius: 8,
                  border: isActive ? `2px solid ${color}` : `2px solid ${darkMode ? '#334155' : '#e2e8f0'}`,
                  background: isActive ? `${color}18` : (darkMode ? '#0f172a' : '#f8fafc'),
                  cursor: 'pointer',
                  fontSize: 13,
                  fontWeight: isActive ? 700 : 500,
                  color: isActive ? color : (darkMode ? '#94a3b8' : '#475569'),
                  transition: 'all 0.12s',
                  textAlign: 'left',
                }}
              >
                <span style={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  backgroundColor: color,
                  flexShrink: 0,
                }} />
                {DISPOSITION_LABELS[d]}
              </button>
            )
          })}
        </div>

        {/* Notes textarea */}
        <textarea
          placeholder="Notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value.slice(0, 1000))}
          maxLength={1000}
          rows={3}
          style={{
            width: '100%',
            padding: '8px 10px',
            borderRadius: 8,
            border: `1px solid ${darkMode ? '#334155' : '#e2e8f0'}`,
            background: darkMode ? '#0f172a' : '#f8fafc',
            color: darkMode ? '#f1f5f9' : '#0f172a',
            fontSize: 13,
            resize: 'vertical',
            boxSizing: 'border-box',
            marginBottom: 4,
            fontFamily: 'inherit',
          }}
        />
        <div style={{
          fontSize: 11,
          color: darkMode ? '#475569' : '#94a3b8',
          textAlign: 'right',
          marginBottom: 16,
        }}>
          {notes.length}/1000
        </div>

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={onCancel}
            style={{
              flex: 1,
              padding: '10px 0',
              borderRadius: 8,
              border: `1px solid ${darkMode ? '#334155' : '#e2e8f0'}`,
              background: 'transparent',
              color: darkMode ? '#94a3b8' : '#64748b',
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(selected, notes)}
            disabled={isLoading}
            style={{
              flex: 2,
              padding: '10px 0',
              borderRadius: 8,
              border: 'none',
              background: DISPOSITION_COLORS[selected],
              color: '#ffffff',
              fontSize: 14,
              fontWeight: 700,
              cursor: isLoading ? 'wait' : 'pointer',
              opacity: isLoading ? 0.7 : 1,
            }}
          >
            {isLoading ? 'Saving...' : 'Save Pin'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ===== Pin Detail View =====

interface PinDetailProps {
  pin: LeadPinResponse
  onBack: () => void
}

function PinDetail({ pin, onBack }: PinDetailProps) {
  const darkMode = useAppStore((s) => s.darkMode)
  const setSelectedLeadPinId = useAppStore((s) => s.setSelectedLeadPinId)
  const { data: activitiesData, isLoading: activitiesLoading } = useLeadPinActivities(pin.id)
  const updatePin = useUpdateLeadPin()
  const deletePin = useDeleteLeadPin()
  const createActivity = useCreatePinActivity()
  const [showUpdatePicker, setShowUpdatePicker] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [showLogNote, setShowLogNote] = useState(false)
  const [noteText, setNoteText] = useState('')

  const handleUpdate = (disposition: LeadPinDisposition, notes: string) => {
    updatePin.mutate(
      { pinId: pin.id, data: { disposition, notes } },
      {
        onSuccess: () => {
          setShowUpdatePicker(false)
        },
      },
    )
  }

  const handleDelete = () => {
    deletePin.mutate(pin.id, {
      onSuccess: () => {
        setSelectedLeadPinId(null)
      },
    })
  }

  const handleLogNote = () => {
    if (!noteText.trim()) return
    createActivity.mutate(
      { pinId: pin.id, data: { notes: noteText.trim() } },
      {
        onSuccess: () => {
          setNoteText('')
          setShowLogNote(false)
        },
      },
    )
  }

  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'
  const borderColor = darkMode ? '#334155' : '#e2e8f0'
  const bgSecondary = darkMode ? '#1e293b' : '#f8fafc'

  return (
    <div>
      {showUpdatePicker && (
        <DispositionPicker
          title="Update Disposition"
          initialDisposition={pin.disposition}
          initialNotes={pin.notes ?? ''}
          onConfirm={handleUpdate}
          onCancel={() => setShowUpdatePicker(false)}
          isLoading={updatePin.isPending}
        />
      )}

      <button
        onClick={onBack}
        style={{
          background: 'none',
          border: 'none',
          color: '#2563eb',
          cursor: 'pointer',
          fontSize: 14,
          padding: 0,
          marginBottom: 12,
        }}
      >
        Back to list
      </button>

      {/* Pin header */}
      <div style={{
        background: bgSecondary,
        borderRadius: 10,
        padding: 12,
        marginBottom: 12,
        border: `1px solid ${borderColor}`,
      }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: textPrimary, marginBottom: 6 }}>
          {pin.address || 'Dropped pin'}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <DispositionBadge disposition={pin.disposition} />
          <span style={{ fontSize: 12, color: textSecondary }}>
            {timeAgo(pin.created_at)}
          </span>
        </div>
        {pin.notes && (
          <div style={{
            marginTop: 8,
            fontSize: 13,
            color: textSecondary,
            lineHeight: '1.5',
            padding: '8px 10px',
            background: darkMode ? '#0f172a' : '#ffffff',
            borderRadius: 6,
            border: `1px solid ${borderColor}`,
          }}>
            {pin.notes}
          </div>
        )}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          onClick={() => setShowUpdatePicker(true)}
          style={{
            flex: 1,
            padding: '8px 0',
            borderRadius: 8,
            border: '1px solid #2563eb',
            background: 'transparent',
            color: '#2563eb',
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Update
        </button>
        {!confirmDelete ? (
          <button
            onClick={() => setConfirmDelete(true)}
            style={{
              flex: 1,
              padding: '8px 0',
              borderRadius: 8,
              border: '1px solid #ef4444',
              background: 'transparent',
              color: '#ef4444',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Delete
          </button>
        ) : (
          <button
            onClick={handleDelete}
            disabled={deletePin.isPending}
            style={{
              flex: 1,
              padding: '8px 0',
              borderRadius: 8,
              border: 'none',
              background: '#ef4444',
              color: '#ffffff',
              fontSize: 13,
              fontWeight: 700,
              cursor: deletePin.isPending ? 'wait' : 'pointer',
              opacity: deletePin.isPending ? 0.7 : 1,
            }}
          >
            {deletePin.isPending ? 'Deleting...' : 'Confirm Delete'}
          </button>
        )}
      </div>
      {confirmDelete && (
        <button
          onClick={() => setConfirmDelete(false)}
          style={{
            width: '100%',
            padding: '6px 0',
            borderRadius: 8,
            border: `1px solid ${borderColor}`,
            background: 'transparent',
            color: textSecondary,
            fontSize: 12,
            cursor: 'pointer',
            marginBottom: 12,
          }}
        >
          Cancel delete
        </button>
      )}

      {/* Log Note */}
      {!showLogNote ? (
        <button
          onClick={() => setShowLogNote(true)}
          style={{
            width: '100%',
            padding: '8px 0',
            borderRadius: 8,
            border: '1px solid #16a34a',
            background: 'transparent',
            color: '#16a34a',
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
            marginBottom: 16,
          }}
        >
          Log Note
        </button>
      ) : (
        <div style={{ marginBottom: 16 }}>
          <textarea
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            placeholder="Add a note about this visit..."
            maxLength={1000}
            style={{
              width: '100%',
              minHeight: 72,
              padding: 10,
              borderRadius: 8,
              border: `1px solid ${borderColor}`,
              background: darkMode ? '#0f172a' : '#ffffff',
              color: darkMode ? '#f1f5f9' : '#0f172a',
              fontSize: 13,
              lineHeight: '1.5',
              resize: 'vertical',
              boxSizing: 'border-box',
              marginBottom: 8,
            }}
            autoFocus
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleLogNote}
              disabled={!noteText.trim() || createActivity.isPending}
              style={{
                flex: 1,
                padding: '7px 0',
                borderRadius: 8,
                border: 'none',
                background: '#16a34a',
                color: '#ffffff',
                fontSize: 13,
                fontWeight: 600,
                cursor: !noteText.trim() || createActivity.isPending ? 'not-allowed' : 'pointer',
                opacity: !noteText.trim() || createActivity.isPending ? 0.5 : 1,
              }}
            >
              {createActivity.isPending ? 'Saving...' : 'Save Note'}
            </button>
            <button
              onClick={() => { setShowLogNote(false); setNoteText('') }}
              style={{
                flex: 1,
                padding: '7px 0',
                borderRadius: 8,
                border: `1px solid ${borderColor}`,
                background: 'transparent',
                color: textSecondary,
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Activity timeline */}
      <div style={{ fontSize: 13, fontWeight: 600, color: textSecondary, marginBottom: 8 }}>
        Activity History
      </div>
      {activitiesLoading && (
        <div style={{ fontSize: 13, color: textSecondary, textAlign: 'center', padding: 16 }}>
          Loading...
        </div>
      )}
      {activitiesData && activitiesData.activities.length === 0 && (
        <div style={{ fontSize: 13, color: textSecondary, textAlign: 'center', padding: 16 }}>
          No activity yet
        </div>
      )}
      {activitiesData && activitiesData.activities.length > 0 && (
        <div style={{
          maxHeight: 280,
          overflowY: 'auto',
          borderRadius: 8,
          border: `1px solid ${borderColor}`,
        }}>
          {activitiesData.activities.map((activity, i) => (
            <div
              key={activity.id}
              style={{
                padding: '10px 12px',
                borderBottom: i < activitiesData.activities.length - 1
                  ? `1px solid ${borderColor}`
                  : 'none',
                background: i % 2 === 0 ? bgSecondary : (darkMode ? '#0f172a' : '#ffffff'),
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                <DispositionBadge disposition={activity.disposition} />
                <span style={{ fontSize: 11, color: textSecondary }}>
                  {timeAgo(activity.created_at)}
                </span>
              </div>
              {activity.notes && (
                <div style={{ fontSize: 12, color: textSecondary, lineHeight: '1.4', marginTop: 4 }}>
                  {activity.notes}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ===== Main LeadPinPanel =====

function LeadPinPanel() {
  const darkMode = useAppStore((s) => s.darkMode)
  const isPinDropMode = useAppStore((s) => s.isPinDropMode)
  const setIsPinDropMode = useAppStore((s) => s.setIsPinDropMode)
  const selectedLeadPinId = useAppStore((s) => s.selectedLeadPinId)
  const setSelectedLeadPinId = useAppStore((s) => s.setSelectedLeadPinId)

  const { data: pinsData, isLoading: pinsLoading } = useLeadPins()

  const textPrimary = darkMode ? '#f1f5f9' : '#0f172a'
  const textSecondary = darkMode ? '#94a3b8' : '#64748b'
  const borderColor = darkMode ? '#334155' : '#e2e8f0'
  const bgSecondary = darkMode ? '#1e293b' : '#f8fafc'
  const cardBg = darkMode ? '#0f172a' : '#ffffff'

  // Find the selected pin object for detail view
  const selectedPin = selectedLeadPinId
    ? pinsData?.pins.find((p) => p.id === selectedLeadPinId) ?? null
    : null

  return (
    <div style={{ padding: 16 }}>

      {/* Pin detail view */}
      {selectedLeadPinId && selectedPin && (
        <PinDetail
          pin={selectedPin}
          onBack={() => setSelectedLeadPinId(null)}
        />
      )}

      {/* Loading state for selected pin that isn't in local data yet */}
      {selectedLeadPinId && !selectedPin && pinsLoading && (
        <div>
          <button
            onClick={() => setSelectedLeadPinId(null)}
            style={{
              background: 'none',
              border: 'none',
              color: '#2563eb',
              cursor: 'pointer',
              fontSize: 14,
              padding: 0,
              marginBottom: 12,
            }}
          >
            Back to list
          </button>
          <div style={{ fontSize: 13, color: textSecondary, textAlign: 'center', padding: 24 }}>
            Loading pin...
          </div>
        </div>
      )}

      {/* Pin list view — show when no pin is selected */}
      {!selectedLeadPinId && (
        <>
          {/* Header row with pin-drop toggle */}
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 14,
          }}>
            <h3 style={{
              margin: 0,
              fontSize: 15,
              fontWeight: 700,
              color: textPrimary,
            }}>
              Lead Pins
            </h3>
            <button
              onClick={() => setIsPinDropMode(!isPinDropMode)}
              style={{
                padding: '6px 12px',
                borderRadius: 8,
                border: isPinDropMode
                  ? '2px solid #8b5cf6'
                  : `1px solid ${borderColor}`,
                background: isPinDropMode ? '#8b5cf620' : 'transparent',
                color: isPinDropMode ? '#8b5cf6' : textSecondary,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                transition: 'all 0.12s',
              }}
            >
              <span style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: isPinDropMode ? '#8b5cf6' : textSecondary,
              }} />
              {isPinDropMode ? 'Drop mode ON' : 'Drop pin'}
            </button>
          </div>

          {isPinDropMode && (
            <div style={{
              fontSize: 12,
              color: '#8b5cf6',
              background: '#8b5cf610',
              border: '1px solid #8b5cf640',
              borderRadius: 8,
              padding: '8px 12px',
              marginBottom: 12,
              lineHeight: '1.5',
            }}>
              Tap anywhere on the map to drop a pin. Click an existing pin to view it.
            </div>
          )}

          {/* Pin list */}
          {pinsLoading && (
            <div style={{ fontSize: 13, color: textSecondary, textAlign: 'center', padding: 24 }}>
              Loading pins...
            </div>
          )}
          {!pinsLoading && pinsData && pinsData.pins.length === 0 && (
            <div style={{
              fontSize: 13,
              color: textSecondary,
              textAlign: 'center',
              padding: '24px 16px',
              lineHeight: '1.6',
            }}>
              No pins in this area yet.
              {!isPinDropMode && (
                <span> Tap "Drop pin" to start tracking leads.</span>
              )}
            </div>
          )}
          {!pinsLoading && pinsData && pinsData.pins.length > 0 && (
            <>
              <div style={{ fontSize: 11, color: textSecondary, marginBottom: 8 }}>
                {pinsData.total} pin{pinsData.total !== 1 ? 's' : ''} in view
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {pinsData.pins.map((pin) => (
                  <button
                    key={pin.id}
                    onClick={() => setSelectedLeadPinId(pin.id)}
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      borderRadius: 8,
                      border: `1px solid ${borderColor}`,
                      background: cardBg,
                      cursor: 'pointer',
                      textAlign: 'left',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 8,
                      transition: 'background 0.12s',
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLElement).style.background = bgSecondary
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLElement).style.background = cardBg
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
                        marginBottom: 4,
                      }}>
                        {pin.address || 'Dropped pin'}
                      </div>
                      <DispositionBadge disposition={pin.disposition} />
                    </div>
                    <span style={{ fontSize: 11, color: textSecondary, flexShrink: 0 }}>
                      {timeAgo(pin.created_at)}
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

export default LeadPinPanel
